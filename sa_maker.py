#!/usr/bin/env python3
import json
import os
import sys

import click
from loguru import logger

from utils import misc
from utils.google import Google

############################################################
# INIT
############################################################

# Globals
cfg = None
google = None


# Click
@click.group(help='service_account_maker')
@click.version_option('0.0.1', prog_name='service_account_maker')
@click.option('-v', '--verbose', count=True, default=0, help='Adjust the logging level')
@click.option(
    '--config-path',
    envvar='SA_MAKER_CONFIG_PATH',
    type=click.Path(file_okay=True, dir_okay=False),
    help='Configuration filepath',
    show_default=True,
    default=os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "config.json")
)
@click.option(
    '--log-path',
    envvar='SA_MAKER_LOG_PATH',
    type=click.Path(file_okay=True, dir_okay=False),
    help='Log filepath',
    show_default=True,
    default=os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "activity.log")
)
@click.option(
    '--token-path',
    envvar='SA_MAKER_TOKEN_PATH',
    type=click.Path(file_okay=True, dir_okay=False),
    help='Token filepath',
    show_default=True,
    default=os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "token.json")
)
def app(verbose, config_path, log_path, token_path):
    global cfg, google

    # Ensure paths are full paths
    if not config_path.startswith(os.path.sep):
        config_path = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), config_path)
    if not log_path.startswith(os.path.sep):
        log_path = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), log_path)
    if not token_path.startswith(os.path.sep):
        token_path = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), token_path)

    # Load config
    from utils.config import Config
    cfg = Config(config_path=config_path).cfg

    # Load logger
    log_levels = {0: 'INFO', 1: 'DEBUG', 2: 'TRACE'}
    log_level = log_levels[verbose] if verbose in log_levels else 'TRACE'
    config_logger = {
        'handlers': [
            {'sink': sys.stdout, 'backtrace': True if verbose >= 2 else False, 'level': log_level},
            {'sink': log_path,
             'rotation': '30 days',
             'retention': '7 days',
             'enqueue': True,
             'backtrace': True if verbose >= 2 else False,
             'level': log_level}
        ]
    }
    logger.configure(**config_logger)

    # Load google
    google = Google(cfg.client_id, cfg.client_secret, cfg.project_name, token_path)

    # Display params
    logger.info("%s = %r" % ("LOG_PATH".ljust(12), log_path))
    logger.info("%s = %r" % ("LOG_LEVEL".ljust(12), log_level))
    logger.info("")
    return


############################################################
# CLICK FUNCTIONS
############################################################

@app.command(help='Authorize Google Account')
def authorize():
    global google, cfg

    logger.debug(f"client_id: {cfg.client_id!r}")
    logger.debug(f"client_secret: {cfg.client_secret!r}")

    # Provide authorization link
    logger.info("Visit the link below and paste the authorization code")
    logger.info(google.get_auth_link())
    logger.info("Enter authorization code: ")
    auth_code = input()
    logger.debug(f"auth_code: {auth_code!r}")

    # Exchange authorization code
    token = google.exchange_code(auth_code)
    if not token or 'access_token' not in token:
        logger.error("Failed exchanging authorization code for an access token....")
        sys.exit(1)
    else:
        logger.info(f"Exchanged authorization code for an access token:\n\n{json.dumps(token, indent=2)}\n")
    sys.exit(0)


@app.command(help='Retrieve existing service accounts')
def list_accounts():
    global google, cfg

    # retrieve service accounts
    logger.info("Retrieving existing service accounts...")
    success, service_accounts = google.get_service_accounts()
    if success:
        logger.info(f"Existing service accounts:\n{json.dumps(service_accounts, indent=2)}")
        sys.exit(0)
    else:
        logger.error(f"Failed to retrieve service accounts:\n{service_accounts}")
        sys.exit(1)


@app.command(help='Create service accounts')
@click.option('--name', '-n', required=True, help='Name prefix for service accounts')
@click.option('--amount', '-a', default=1, required=False, help='Amount of service accounts to create')
def create_accounts(name, amount=1):
    global google, cfg

    service_key_folder = os.path.join(cfg.service_account_folder, name)

    # does service key subfolder exist?
    if not os.path.exists(service_key_folder):
        logger.debug(f"Creating service key path: {service_key_folder!r}")
        if os.makedirs(service_key_folder, exist_ok=True):
            logger.info(f"Created service key path: {service_key_folder!r}")

    # count amount of service files that exist already in this folder
    starting_account_number = misc.get_starting_account_number(service_key_folder)
    if not starting_account_number:
        logger.error(f"Failed to determining the account number to start from....")
        sys.exit(1)

    for account_number in range(starting_account_number, starting_account_number + amount):
        account_name = f'{name}{account_number:06d}'

        # create the service account
        success, service_account = google.create_service_account(account_name)
        if success and (isinstance(service_account, dict) and 'email' in service_account and
                        'uniqueId' in service_account):
            account_email = service_account['email']
            logger.info(f"Created service account: {account_email!r}")

            # create key for new service account
            success, service_key = google.create_service_account_key(account_email)
            if success and (isinstance(service_key, dict) and 'privateKeyData' in service_key):
                service_key_path = os.path.join(service_key_folder, f'{account_number}.json')
                if misc.dump_service_file(service_key_path, service_key):
                    logger.info(f"Created service key for account {account_email!r}: {service_key_path}")
                else:
                    logger.error(f"Created service key for account, but failed to dump it to: {service_key_path}")
                    sys.exit(1)
            else:
                logger.error(f"Failed to create service key for account {account_email!r}:\n{service_key}\n")
                sys.exit(1)
        else:
            logger.error(f"Failed to create service account {account_name!r}:\n{service_account}\n")
            sys.exit(1)


@app.command(help='Retrieve existing teamdrives')
def list_teamdrives():
    global google, cfg

    success, teamdrives = google.get_teamdrives()
    if success:
        logger.info(f'Existing teamdrives:\n{json.dumps(teamdrives, indent=2)}')
        sys.exit(0)
    else:
        logger.error(f'Failed to retrieve teamdrives:\n{teamdrives}')
        sys.exit(1)


@app.command(help='Create teamdrive')
@click.option('--name', '-n', required=True, help='Name of the new teamdrive')
def create_teamdrive(name):
    global google, cfg

    success, teamdrive = google.create_teamdrive(name)
    if success:
        logger.info(f'Created teamdrive {name!r}:\n{teamdrive}')
        sys.exit(0)
    else:
        logger.error(f'Failed to create teamdrive {name!r}:\n{teamdrive}')
        sys.exit(1)


@app.command(help='Set users for a teamdrive')
@click.option('--name', '-n', required=True, help='Name of the existing teamdrive')
@click.option('--key-prefix', '-k', required=True, help='Name prefix of service accounts')
def set_teamdrive_users(name, key_prefix):
    global google, cfg

    # validate the service key folder exists
    service_key_folder = os.path.join(cfg.service_account_folder, key_prefix)
    if not os.path.exists(service_key_folder):
        logger.error(f"The service key folder did not exist at: {service_key_folder}")
        sys.exit(1)

    # retrieve service key users to share teamdrive access with
    service_key_users = misc.get_service_account_users(service_key_folder)
    if service_key_users is None:
        logger.error(f"Failed to determine the service key user(s) to share with teamdrive: {name}")
        sys.exit(1)

    # retrieve teamdrive id
    success, teamdrives = google.get_teamdrives()
    if not success:
        logger.error(f"Unable to retrieve existing teamdrives:\n{teamdrives}")
        sys.exit(1)

    teamdrive_id = misc.get_teamdrive_id(teamdrives, name)
    if not teamdrive_id:
        logger.error(f"Failed to determine teamdrive_id of teamdrive with name {name!r}")
        sys.exit(1)

    logger.info(
        f"Sharing access to {name!r} teamdrive for {len(service_key_users)} service key user(s): {service_key_users}")

    # share access to teamdrive
    for service_key_user in service_key_users:
        success, resp = google.set_teamdrive_share_user(teamdrive_id, service_key_user)
        if success:
            logger.info(f"Shared access to {name!r} teamdrive for user: {service_key_user}")
        else:
            logger.error(f"Failed sharing access to {name!r} teamdrive for user {service_key_user!r}:\n{resp}")
            sys.exit(1)
    sys.exit(0)


############################################################
# MAIN
############################################################

if __name__ == "__main__":
    app()
