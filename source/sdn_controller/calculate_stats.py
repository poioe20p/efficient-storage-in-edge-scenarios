import eventlet
eventlet.monkey_patch()
from datetime import datetime
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from os_ken.lib.packet import ethernet, ether_types, packet
from os_ken.ofproto import ofproto_v1_3
from sdn_controller.models.mongodb_host import MongodbRouter
from sdn_controller.repositories.repositories.event import EventRepository
from sdn_controller.repositories.models.event import Event

class CalculateSwitchPortDebit(app_manager.OSKenApp):
        OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(CalculateSwitchPortDebit, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.enable_reactive_learning = True

        