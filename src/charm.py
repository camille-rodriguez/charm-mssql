#!/usr/bin/env python3

import sys
sys.path.append('lib')

from base64 import b64encode
from ops.charm import CharmBase, CharmEvents
from ops.framework import EventSource, EventBase, StoredState
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.main import main

import logging
import subprocess

import yaml

logger = logging.getLogger()



class MSSQLReadyEvent(EventBase):
    pass


class MSSQLCharmEvents(CharmEvents):
    mssql_ready = EventSource(MSSQLReadyEvent)


class Charm(CharmBase):
    on = MSSQLCharmEvents()
    state = StoredState()

    def __init__(self, parent, key):
        super().__init__(parent, key)

        self.framework.observe(self.on.install, self.set_pod_spec)
        # self.framework.observe(self.on.start, self)
        self.framework.observe(self.on.stop, self)
        self.framework.observe(self.on.config_changed, self)
        self.framework.observe(self.on.db_relation_joined, self)
        self.framework.observe(self.on.db_relation_changed, self)
        self.framework.observe(self.on.mssql_ready, self)
        self.state.set_default(spec=None)

    def on_stop(self, event):
        log('Ran on_stop')

    def on_config_changed(self, event):
        log('Ran on_config_changed hook')
        self.set_pod_spec(event)

    def on_mssql_ready(self, event):
        pass

    def on_db_relation_joined(self, event):
        self._state['on_db_relation_joined'].append(type(event))
        self._state['observed_event_types'].append(type(event))
        self._state['db_relation_joined_data'] = event.snapshot()
        self._write_state()

    def on_db_relation_changed(self, event):
        if not self.state.ready:
            event.defer()
            return

    def set_pod_spec(self, event):
        if not self.model.unit.is_leader():
            print('Not a leader, skipping set_pod_spec')
            self.model.unit.status = ActiveStatus()
            return

        self.model.unit.status = MaintenanceStatus('Setting pod spec')

        config = self.framework.model.config
        container_config= self.sanitized_container_config()
        config_with_secrets = self.full_container_config()
        # if config_with_secrets is None:
        #     return None
        container_config.update(config_with_secrets)

        ports = yaml.safe_load(self.framework.model.config["ports"])
        if not isinstance(ports, list):
            self.model.unit.status = \
                BlockedStatus("ports is not a list of YAMLs")
            return


        if container_config is not None:
            self.framework.model.pod.set_spec({
                'version': 3,
                'containers': [{
                    'name': self.framework.model.app.name,
                    'image': config["image"],
                    'ports': ports,
                    'envConfig': {
                        # container_config,
                        'MSSQL_PID': 'developer',
                        'ACCEPT_EULA': 'Y',
                        'mssql-secret': {
                            'secret': {
                                'name': 'mssql'
                            }
                        },
                    }
                }],
                'kubernetesResources': {
                    'secrets': [
                        {
                            'name': 'mssql',
                            'type': 'Opaque',
                            'data': {
                                'SA_PASSWORD': (b64encode(
                                    ('MyC0m9l&xP@ssw0rd').encode(
                                        'utf-8')).decode('utf-8')),
                            }
                        }
                    ]
                },
                'serviceAccount': {
                    'roles': [{
                        'global': True,
                        'rules': [
                            {
                                'apiGroups': ['apps'],
                                'resources': ['statefulsets', 'deployments'],
                                'verbs': ['*'],
                            },
                            {
                                'apiGroups': [''],
                                'resources': ['pods', 'pods/exec'],
                                'verbs': ['create', 'get', 'list', 'watch',
                                          'update',
                                          'patch'],
                            },
                            {
                                'apiGroups': [''],
                                'resources': ['configmaps'],
                                'verbs': ['get', 'watch', 'list'],
                            },
                            {
                                'apiGroups': [''],
                                'resources': ['persistentvolumeclaims'],
                                'verbs': ['create', 'delete'],
                            },
                        ],
                    }]
                },

                # "restartPolicy": 'Always',
                # "terminationGracePeriodSeconds": 10,

            })
            self.model.unit.status = ActiveStatus()
        return

    def sanitized_container_config(self):
        """Uninterpolated container config without secrets"""
        config = self.framework.model.config
        if config["container_config"].strip() == "":
            container_config = {}
        else:
            container_config = \
                yaml.safe_load(self.framework.model.config["container_config"])
            if not isinstance(container_config, dict):
                self.framework.model.unit.status = \
                    BlockedStatus("container_config is not a YAML mapping")
                return None
        return container_config

    def full_container_config(self):
        """Uninterpolated container config with secrets"""
        config = self.framework.model.config
        container_config = self.sanitized_container_config()
        if container_config is None:
            return None
        if config["container_secrets"].strip() == "":
            container_secrets = {}
        else:
            container_secrets = yaml.safe_load(config["container_secrets"])
            if not isinstance(container_secrets, dict):
                self.framework.model.unit.status = \
                    BlockedStatus("container_secrets is not a YAML mapping")
                return None
        container_config.update(container_secrets)
        return container_config


def log(message, level=None):
    """Write a message to the juju log"""
    command = ['juju-log']
    if level:
        command += ['-l', level]
    if not isinstance(message, str):
        message = repr(message)

    # https://elixir.bootlin.com/linux/latest/source/include/uapi/linux/binfmts.h
    # PAGE_SIZE * 32 = 4096 * 32
    MAX_ARG_STRLEN = 131072
    command += [message[:MAX_ARG_STRLEN]]
    # Missing juju-log should not cause failures in unit tests
    # Send log output to stderr
    subprocess.call(command)


if __name__ == '__main__':
    main(Charm)
