from strato.racktest.infra.suite import *
import logging


class Test:

    ABORT_TEST_TIMEOUT = 60 * 20

    HOSTS_PER_CLUSTER = 2

    HOSTS = {'sourceCluster':
             {'src_node%d' % i: {'rootfs': 'rootfs-vanilla'}
              for i in range(HOSTS_PER_CLUSTER)},
             'destCluster':
             {'dst_node%d' % i: {'rootfs': 'rootfs-vanilla'}
              for i in range(HOSTS_PER_CLUSTER)
              }}

    HOSTS.update({'multicluster': True})

    def run(self):
        host.src_node1.ssh.run.script('echo hi')
