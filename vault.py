from will import settings
from will.plugin import WillPlugin
from will.decorators import respond_to, require_settings

import requests
import json


class VaultClient(object):

    def __init__(self, server, port, role):
        self.server = server
        self.port = port
        self.login_url = "https://{server}:{port}/v1/auth/aws/login".format(
                                                                    server=self.server,
                                                                    port=self.port)
        self.nonce = self._get_account_id()
        self.pkcs7 = self._get_pkcs7()
        self.role = role
        self.payload = {"role": self.role,
                        "pkcs7": self.pkcs7,
                        "nonce": self.nonce
                        }
        r = requests.post(self.login_url, data=json.dumps(self.payload))
        if r.status_code == 200:
            output_dict = r.json()
            self.token = output_dict['auth']['client_token']
        else:
            self.token = None

        self.access_key = None
        self.secret_key = None

    def _get_account_id(self):

       url = "http://169.254.169.254/latest/dynamic/instance-identity/document"
       r = requests.get(url)

       if r.status_code == 200:
           output_dict = r.json()
           return output_dict['accountId']
       else:
           return None

    def _get_pkcs7(self):

        url = "http://169.254.169.254/latest/dynamic/instance-identity/pkcs7"
        r = requests.get(url)

        if r.status_code == 200:
            output = r.text
            return output.replace('\n','')
        else:
            return None
    def read_path(self, path):
        url = "https://{server}:{port}/v1/{path}".format(
                                            server=self.server,
                                            port=self.port,
                                            path=path)

        headers = {'X-Vault-Token': self.token}
        r = requests.get(url, headers=headers)

        if r.status_code == 200:
            return r.json()
        else:
            return None

    def generate_aws_keys(self, backend):
        path = "{backend}/creds/{backend}-swe".format(backend=backend)
        output_dict = self.read_path(path)

        if output_dict:
            self.access_key = output_dict['data']['access_key']
            self.secret_key = output_dict['data']['secret_key']
            return True
        else:
            return False


class VaultClientPlugin(WillPlugin):

    @require_settings("VAULT_SERVER", "VAULT_PORT")
    @respond_to("^generate aws keys*(?P<account>.*$)")
    def generate_aws_keys(self, message, account):
        '''generate aws keys [production/staging]: Generate temporary AWS keys'''

        role = 'amy-generate-keys-read-only'
        backend = 'production' if (account.strip() == 'production') else 'staging'
        nick = message.sender["nick"]
        hipchat_uid = message.sender["hipchat_id"]
        nick_key = "{0}_{1}_aws_creds_valid".format(nick, backend)

        # Check if the last set of keys the user generated is
        # still valid
        if self.load(nick_key):
            response = "Previously generated keys still valid, please re-use."
        else:
            v = VaultClient(settings.VAULT_SERVER, settings.VAULT_PORT, role)

            if v.token:
                v.generate_aws_keys(backend)
            else:
                response = "Failed to get Vault token, please ping Automatoes oncall"

            if v.access_key and v.secret_key:
                self.save(nick_key, True, expire=3600)
                response = "Account: {backend}\nAccess Key: {access_key}\nSecret Key: {secret_key}".format(
                                                                backend=backend,
                                                                access_key=v.access_key,
                                                                secret_key=v.secret_key)
            else:
                response = "Failed to generate {backend} AWS credentials, please ping Automatoes oncall".format(
                                                                backend=backend)

        # If groupchat notify in room
        if message['type'] == 'groupchat':
            room = self.get_room_from_message(message)
            self.say("@{0} PM'ed the details".format(nick), room=room)

        # Private message the keys/error
        self.send_direct_message(hipchat_uid, response)


    @require_settings("VAULT_SERVER", "VAULT_PORT")
    @respond_to("^get\s*(?P<path>secret(\/\S*){4}).*from.*consul.*")
    def get_value_from_vault(self, message, path):
        '''get secret/../../../KEY from consul: Fetch value from consul (works only in private messages)'''
        role = 'read-only-production'
        if message['type'] != 'groupchat':
            v = VaultClient(settings.VAULT_SERVER, settings.VAULT_PORT, role)
            if v.token:
                output_dict = v.read_path(path.strip())
                if output_dict:
                    response = "{value}".format(value=output_dict['data']['value'])
                else:
                    response = "Error reading value, does {path} exist?".format(path=path.strip())
            else:
                response = "Failed to get Vault token, please ping Automatoes oncall"

            hipchat_uid = message.sender["hipchat_id"]
            self.send_direct_message(hipchat_uid, response)
        else:
            nick = message.sender["nick"]
            room = self.get_room_from_message(message)
            self.say("@{0} I do not share secrets in public :\\".format(nick), room=room)
