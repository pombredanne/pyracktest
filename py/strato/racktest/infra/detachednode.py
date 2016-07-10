from rackattack import api
from rackattack import clientfactory
from rackattack.tcp import node


class DetachedNode(node.Node):
    def __init__(self, username, password, hostname, port, ipAddress, nodeId, info):
        self._username = username
        self._password = password
        self._hostname = hostname
        self._port = port
        self._ipAddress = ipAddress
        self._id = nodeId
        self._info = info
        self._ipcClient = clientfactory.factory()

    def rootSSHCredentials(self):
        return dict(hostname=self._hostname,
                    username=self._username,
                    password=self._password,
                    key=None,
                    port=self._port)

    def ipAddress(self):
        return self._ipAddress
