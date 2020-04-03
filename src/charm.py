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


class MSSQLCharm(CharmBase):
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

        log('Adding secret to container_config', level='INFO')
        config = self.framework.model.config
        container_config= self.sanitized_container_config()
        container_config['mssql-secret'] = {'secret' : {'name': 'mssql'}}

        log('Validating ports syntax', level='INFO')
        ports = yaml.safe_load(self.framework.model.config["ports"])
        if not isinstance(ports, list):
            self.model.unit.status = \
                BlockedStatus("ports is not a list of YAMLs")
            return

        log('Validating password', level='INFO')
        check_password = self.framework.model.config["sa_password"]
        if len(check_password) < 8 \
                or len(check_password) > 20 \
                or not any(char.isupper() for char in check_password) \
                or not any(char.islower() for char in check_password) \
                or not any(char.isdigit() for char in check_password) \
                or not any(char in ['!', '@', '$', '%', '?', '&', '*']
                           for char in check_password):
            self.model.unit.status = \
                BlockedStatus("sa_password does not respect criteria")
            return
        sa_password = b64encode((check_password).
                                encode('utf-8')).decode('utf-8')

        log('Setting pod spec', level='INFO')
        self.framework.model.pod.set_spec({
            'version': 3,
            'containers': [{
                'name': self.framework.model.app.name,
                'image': config["image"],
                'ports': ports,
                'envConfig': container_config,
                }
            ],
            'kubernetesResources': {
                'secrets': [
                    {
                        'name': 'mssql',
                        'type': 'Opaque',
                        'data': {
                            'SA_PASSWORD': sa_password,
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
    main(MSSQLCharm)
