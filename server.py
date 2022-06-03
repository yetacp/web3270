import tornado.web
from tornado.ioloop import IOLoop
from terminado import TermSocket, TermManagerBase
import os
import signal
import configparser
import argparse
import shutil
import secrets

warnings = [
    '''
██     ██  █████  ██████  ███    ██ ██ ███    ██  ██████  
██     ██ ██   ██ ██   ██ ████   ██ ██ ████   ██ ██       
██  █  ██ ███████ ██████  ██ ██  ██ ██ ██ ██  ██ ██   ███ 
██ ███ ██ ██   ██ ██   ██ ██  ██ ██ ██ ██  ██ ██ ██    ██ 
 ███ ███  ██   ██ ██   ██ ██   ████ ██ ██   ████  ██████''',
    '''
 █     █░ ▄▄▄       ██▀███   ███▄    █  ██▓ ███▄    █   ▄████ 
▓█░ █ ░█░▒████▄    ▓██ ▒ ██▒ ██ ▀█   █ ▓██▒ ██ ▀█   █  ██▒ ▀█▒
▒█░ █ ░█ ▒██  ▀█▄  ▓██ ░▄█ ▒▓██  ▀█ ██▒▒██▒▓██  ▀█ ██▒▒██░▄▄▄░
░█░ █ ░█ ░██▄▄▄▄██ ▒██▀▀█▄  ▓██▒  ▐▌██▒░██░▓██▒  ▐▌██▒░▓█  ██▓
░░██▒██▓  ▓█   ▓██▒░██▓ ▒██▒▒██░   ▓██░░██░▒██░   ▓██░░▒▓███▀▒
░ ▓░▒ ▒   ▒▒   ▓▒█░░ ▒▓ ░▒▓░░ ▒░   ▒ ▒ ░▓  ░ ▒░   ▒ ▒  ░▒   ▒ 
  ▒ ░ ░    ▒   ▒▒ ░  ░▒ ░ ▒░░ ░░   ░ ▒░ ▒ ░░ ░░   ░ ▒░  ░   ░ 
  ░   ░    ░   ▒     ░░   ░    ░   ░ ░  ▒ ░   ░   ░ ░ ░ ░   ░ 
    ░          ░  ░   ░              ░  ░           ░       ░ 
''',
    '''
██╗    ██╗ █████╗ ██████╗ ███╗   ██╗██╗███╗   ██╗ ██████╗ 
██║    ██║██╔══██╗██╔══██╗████╗  ██║██║████╗  ██║██╔════╝ 
██║ █╗ ██║███████║██████╔╝██╔██╗ ██║██║██╔██╗ ██║██║  ███╗
██║███╗██║██╔══██║██╔══██╗██║╚██╗██║██║██║╚██╗██║██║   ██║
╚███╔███╔╝██║  ██║██║  ██║██║ ╚████║██║██║ ╚████║╚██████╔╝
 ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═══╝ ╚═════╝ 
'''
]


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        return self.get_secure_cookie("user")


class TerminalPageHandler(BaseHandler):

    def initialize(self, width=80, height=25):
        self.width = width
        self.height = height

    def get(self):
        print("[+] User logging in:", self.current_user)
        return self.render(
            "index.html",
            width=self.width,
            height=self.height,
            ws_url_path="/websocket"
        )


class Unique3270Manager(TermManagerBase):
    """Give each websocket a unique terminal to use."""

    def __init__(self, max_terminals=None, theight=45, twidth=80, **kwargs):
        super(Unique3270Manager, self).__init__(**kwargs)
        self.max_terminals = max_terminals
        self.height = theight
        self.width = twidth

    def get_terminal(self, url_component=None):
        if self.max_terminals and len(self.ptys_by_fd) >= self.max_terminals:
            raise MaxTerminalsReached(self.max_terminals)

        term = self.new_terminal(height=self.height, width=self.width)
        self.start_reading(term)
        return term

    def client_disconnected(self, websocket):
        """Send terminal SIGHUP when client disconnects."""
        self.log.info("Websocket closed, sending SIGHUP to terminal.")
        if websocket.terminal:
            if os.name == 'nt':
                websocket.terminal.kill()
                # Immediately call the pty reader to process
                # the eof and free up space
                self.pty_read(websocket.terminal.ptyproc.fd)
                return
            websocket.terminal.killpg(signal.SIGHUP)


parser = argparse.ArgumentParser(
    description='web3270 - Web based front end to c3270')
parser.add_argument('--config', help='web3270 Config folder',
                    default=os.path.dirname(os.path.realpath(__file__)))
args = parser.parse_args()
if not os.path.exists("{}/web3270.ini".format(args.config)):
    print("[+] {}/web3270.ini does not exist, copying".format(args.config))
    shutil.copy2(
        "{}/web3270.ini".format(os.path.dirname(os.path.realpath(__file__))), args.config)

print("[+] Using config: {}/web3270.ini".format(args.config))
config = configparser.ConfigParser(comment_prefixes='/', allow_no_value=True)
config.read("{}/web3270.ini".format(args.config))

if __name__ == '__main__':
    print("[+] Starting Web server")
    # defaults
    height = 45
    width = 80
    c3270 = ['c3270', '-secure', '-defaultfgbg']

    if not config['web']['secret']:
        config['web']['secret'] = secrets.token_urlsafe()
        error = "[+] 'secret =' in {}/web3270.ini is blank. Setting it to: {}".format(
            args.config, config['web']['secret'])
        print(error)
        with open("{}/web3270.ini".format(args.config), 'w') as configfile:
            config.write(configfile)

    c3270.append("-model")
    c3270.append(config['tn3270']['model'])

    if config['tn3270']['model'] == 2:
        height = 24 + 2
    elif config['tn3270']['model'] == 3:
        height = 32 + 2
    elif config['tn3270']['model'] == 4:
        height = 43 + 2
    elif config['tn3270']['model'] == 5:
        height = 27 + 2
        width = 132

    connect_string = ""

    connect_string += config['tn3270']['server_ip'] + \
        ":" + config['tn3270']['server_port']

    c3270.append(connect_string)

    print("[+] c3270 connect string: '{}'".format(' '.join(c3270)))

    term_manager = Unique3270Manager(
        theight=height, twidth=width, shell_command=c3270)
    handlers = [
        (r"/websocket", TermSocket, {'term_manager': term_manager}),
        (r"/", TerminalPageHandler)
    ]
    handlers.append((r"/(.*)", tornado.web.StaticFileHandler, {'path': '.'}))
    app = tornado.web.Application(
        handlers, cookie_secret=config['web']['secret'])

    app.listen(config['web']['webport'])
    print("[+] Web server Listening on port {}".format(config['web']['webport']))
    IOLoop.current().start()
