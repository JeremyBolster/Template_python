# external imports
import click
import yaml
from daemonize import Daemonize

# std lib imports 
import time
import signal
import sys
import logging
import logging.config
import os
from time import sleep
from functools import wraps
from fcntl import flock, LOCK_EX, LOCK_NB

# Log formating is in such a way that you can usually pull out the boilerplate to make for easier viewing
# eg.  
# remove time: cut -c24- /tmp/template-log-file.log
# remove file info: cut -c-34 -c76- /tmp/template-log-file.log


#                              |-23 chars-| |-- 10 chars ---||-------- 41 chars ---------| 
LOG_FORMAT = logging.Formatter('%(asctime)s [%(levelname)-8s][%(filename)-35s:%(lineno)3s] %(message)s')
LOG_FORMAT_THREADED = \
	logging.Formatter('%(asctime)s [%(levelname)-7s][%(threadName)20s-%(thread)2d][%(filename)-35s: %(lineno)3s] %(message)s')


def lock(function):
	"""
	Createa a file level exclusive lock on the a function. 
	It consumes the global variable config['lock_file'].
	"""
	@wraps(function)
	def aquire_lock(*args, **kwargs):
		with open(config['lock_file'], 'a') as lock:
			try:
				flock(lock, LOCK_EX | LOCK_NB)
			except IOError:
				logging.getLogger(__name__).fatal('Unable to get exclusive lock. Exiting.')
				sys.exit(1)

			# Do the thing
			return function(*args, **kwargs)
	return aquire_lock


def process_id(function):
	""" Checks for the running existance of this program. """
	@wraps(function)
	def get_pid(*args, **kwargs):
		if not os.path.isfile(config['pid_file']):
			click.echo('Could not find the pid file')
			sys.exit(1)

		pid = -1
		with open(config['pid_file'], 'r') as f:
			pid = int(f.read())

		try:
			os.kill(pid, 0)
		except OSError:
			click.echo('Pid file found but pid %s is not alive' % pid)
		else:
			return function(pid, *args, **kwargs)
	return get_pid


@click.group()
@click.option('-v', '--verbose', count=True)
@click.argument('config-file', type=click.Path(exists=True, resolve_path=True))
def cli(config_file, verbose):
	
	load_config(config_file) # Loaded as a global for this file only! Do not import this elsewhere.

	log_level = logging.DEBUG if verbose else logging.INFO
	logging_config = config['logging']
	logging_config['handlers']['console']['level'] = log_level
	logging.config.dictConfig(logging_config)
	global file_handler
	file_handler = logging.getLogger().handlers[1]


@cli.command()
@lock
def basic_hello():
	click.echo('Hello World!')
	sleep(10)


@cli.command()
@click.option('--count', default=1, help='Number of greetings.')
@click.option('--name', prompt='Your name',
			  help='The person to greet.')
def hello(count, name):
	"""Simple program that greets NAME for a total of COUNT times."""
	for x in range(count):
		click.echo('Hello %s!' % name)


@cli.group()
def daemon_command():
	pass

@daemon_command.command()
def start():
	
	keep_fds = [file_handler.stream.fileno()]

	daemon = Daemonize(app="my_app_name", pid=config['pid_file'], action=daemon_command_to_be_executed,
					   keep_fds=keep_fds, chdir='/', logger=logging.getLogger(__name__))
	daemon.start()


@daemon_command.command()
@process_id
def stop(pid):
	os.kill(pid, signal.SIGTERM)
	logging.getLogger(__name__).info('Death to %s', pid)


@daemon_command.command()
@process_id
def config_reload(pid):
	os.kill(pid, signal.SIGHUP)


def daemon_command_to_be_executed():
	signal.signal(signal.SIGHUP, load_config_sighup)
	while True:
		sleep(1)
		logging.getLogger(__name__).info('We are a daemon!')


def load_config_sighup(sig, frame):
	logging.getLogger(__name__).info("Reloading config file.")
	load_config(config['config_file'])


def load_config(config_file):
	logging.getLogger(__name__).debug('Attempting to load config from: %s', config_file)
	global config
	with open(config_file, 'r') as f:
		config = yaml.load(f)
	config['config_file'] = config_file



if __name__ == '__main__':
	cli()
