from rackattack import api


class DetachedNode(api.Node):
    def __init__(self, username, password, hostname, port, ipAddress, nodeId):
        self._username = username
        self._password = password
        self._hostname = hostname
        self._port = port
        self._ipAddress = ipAddress
        self._id = id

    def rootSSHCredentials(self):
        return dict(hostname=self._hostname,
                    username=self._username,
                    password=self._password,
                    key=None,
                    port=self._port)

    def ipAddress(self):
        return self._ipAddress

    def id(self):
        return self._id
