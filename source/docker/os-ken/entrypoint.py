import eventlet
eventlet.monkey_patch()

from os_ken.cmd.manager import main
main()
