import os
import logging
import json
import sys
import requests
import configparser
import argparse
import shutil
import time

parser = argparse.ArgumentParser(description='RadarrClean. Compare a Master and Slave radarr instance and delete from the slave.')
parser.add_argument('--config', action="store", type=str, help='Location of config file.')
parser.add_argument('--debug', help='Enable debug logging.', action="store_true")
parser.add_argument('--whatif', help="Read-Only. What would happen if I ran this. No posts are sent. Should be used with --debug", action="store_true")
args = parser.parse_args()

def ConfigSectionMap(section):
    dict1 = {}
    options = Config.options(section)
    for option in options:
        try:
            dict1[option] = Config.get(section, option)
            if dict1[option] == -1:
                logger.debug("skip: %s" % option)
        except:
            print("exception on %s!" % option)
            dict1[option] = None
    return dict1

Config = configparser.ConfigParser()
settingsFilename = os.path.join(os.getcwd(), 'Config.txt')
if args.config:
    settingsFilename = args.config
elif not os.path.isfile(settingsFilename):
    print("Creating default config. Please edit and run again.")
    shutil.copyfile(os.path.join(os.getcwd(), 'Config.default'), settingsFilename)
    sys.exit(0)
Config.read(settingsFilename)

print(ConfigSectionMap('Radarr_PQ')['rootfolders'].split(';'))

########################################################################################################################
logger = logging.getLogger()
if ConfigSectionMap("General")['log_level'] == 'DEBUG':
    logger.setLevel(logging.DEBUG)
elif ConfigSectionMap("General")['log_level'] == 'VERBOSE':
    logger.setLevel(logging.VERBOSE)
else:
    logger.setLevel(logging.INFO)
if args.debug:
    logger.setLevel(logging.DEBUG)

logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")

fileHandler = logging.FileHandler(ConfigSectionMap('General')['log_path'],'w','utf-8')
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)
########################################################################################################################

session = requests.Session()
session.trust_env = False

radarr_url = ConfigSectionMap("RadarrMaster")['url']
radarr_key = ConfigSectionMap("RadarrMaster")['key']
radarrMovies = session.get('{0}/api/movie?apikey={1}'.format(radarr_url, radarr_key))
if radarrMovies.status_code != 200:
    logger.error('Master Radarr server error - response {}'.format(radarrMovies.status_code))
    sys.exit(0)

servers = {}
for section in Config.sections():
    section = str(section)
    if "Radarr_" in section:
        server = (str.split(section,'Radarr_'))[1]
        servers[server] = ConfigSectionMap(section)
        movies = session.get('{0}/api/movie?apikey={1}'.format(servers[server]['url'], servers[server]['key']))
        if movies.status_code != 200:
            logger.error('{0} Radarr server error - response {1}'.format(server, movies.status_code))
            sys.exit(0)
        else:
            servers[server]['movies'] = []
            servers[server]['matchMovies'] = 0
            servers[server]['movieid'] = []
            for movie in movies.json():
                servers[server]['movies'].append(movie['tmdbId'])
                servers[server]['movieid'].append(movie['id'])
for movie in radarrMovies.json():
    for name, server in servers.items():
        if movie['tmdbId'] in server['movies']:
            if 'rootfolders' in server:
                allowedFolders = server['rootfolders'].split(';')
                for folder in allowedFolders:
                    if not folder in movie['path']:
                        continue
            if 'local_path' in server:
                path = str(movie['path']).replace(server['local_path'], server['cloud_path'])
                logging.debug('Updating movie path from: {0} to {1}'.format(movie['path'], path))
            else:
                path = movie['path']
            logging.debug('server: {0}'.format(name))
            logging.debug('title: {0}'.format(movie['title']))
            logging.debug('hasFile: {0}'.format(movie['hasFile']))
            logging.debug('tmdbId: {0}'.format(movie['tmdbId']))
            logging.debug('movieid: {0}'.format(server['movieid']))
            logging.debug('id: {0}'.format(movie['id']))
            logging.debug('path: {0}'.format(path))

            headers = {'Accept': 'application/json',
                       'Content-Type': 'application/json',
                       'X-Api-Key': server['key']
                       }
            data = {'content': 'success'}

            logging.debug('headers: {0}'.format(headers))
            logging.debug('data: {0}'.format(data))
            server['matchMovies'] += 1
            if args.whatif:
                logging.debug('WhatIf: Not actually removing movie from Radarr {0}.'.format(name))
            else:
                if server['matchMovies'] > 0:
                    logging.debug('Sleeping for: {0} seconds.'.format(ConfigSectionMap('General')['wait_between_add']))
                    time.sleep(int(ConfigSectionMap('General')['wait_between_add']))
                r = session.delete('{0}/api/movie/{1}'.format(server['url'], server['movieid']), headers=headers, data=json.dumps(data))
            logger.info('removing {0} from Radarr {1} server'.format(movie['title'], name))
        else:
            logging.debug('{0} not in {1} library'.format(movie['title'], name))
