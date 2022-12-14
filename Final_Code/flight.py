import logging
import time
import json
import numpy as np
import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig

# Specify the uri of the drone to which we want to connect (if your radio
# channel is X, the uri should be 'radio://0/X/2M/E7E7E7E7E7')
uri = 'radio://0/24/2M/E7E7E7E7E7' # <-- FIXME # 24 for SSSH and 48 for NAAG

# Specify the variables we want to log (all at 100 Hz)
variables = [
    # State estimates (custom observer)
    'ae483log.o_x',
    'ae483log.o_y',
    'ae483log.o_z',
    'ae483log.psi',
    'ae483log.theta',
    'ae483log.phi',
    'ae483log.v_x',
    'ae483log.v_y',
    'ae483log.v_z',
    # State estimates (default observer)
    'stateEstimate.x',
    'stateEstimate.y',
    'stateEstimate.z',
    'stateEstimate.yaw',
    'stateEstimate.pitch',
    'stateEstimate.roll',
    'stateEstimate.vx',
    'stateEstimate.vy',
    'stateEstimate.vz',
    # Measurements
    'ae483log.w_x',
    'ae483log.w_y',
    'ae483log.w_z',
    'ae483log.n_x',
    'ae483log.n_y',
    'ae483log.r',
    'ae483log.a_z',
    # lighthouse live measurements that the controller can use 
    'ae483log.lh_x',
    'ae483log.lh_y',
    'ae483log.lh_z',
    # # lighthouse logged data
    # 'lighthouse.x',
    # 'lighthouse.y',
    # 'lighthouse.z',
    # Setpoint (default controller)
    'ctrltarget.x',
    'ctrltarget.y',
    'ctrltarget.z',
    # Setpoint (custom controller)
    'ae483log.o_x_des',
    'ae483log.o_y_des',
    'ae483log.o_z_des',
    # Motor power commands
    ## 'ae483log.m_1',
    ## 'ae483log.m_2',
    ## 'ae483log.m_3',
    ## 'ae483log.m_4',
    'motor.m1',
    'motor.m2',
    'motor.m3',
    'motor.m4',
]

class SimpleClient:
    def __init__(self, uri, use_controller=False, use_observer=False):
        self.init_time = time.time()
        self.use_controller = use_controller
        self.use_observer = use_observer
        self.cf = Crazyflie(rw_cache='./cache')
        self.cf.connected.add_callback(self.connected)
        self.cf.fully_connected.add_callback(self.fully_connected)
        self.cf.connection_failed.add_callback(self.connection_failed)
        self.cf.connection_lost.add_callback(self.connection_lost)
        self.cf.disconnected.add_callback(self.disconnected)
        print(f'Connecting to {uri}')
        self.cf.open_link(uri)
        self.is_fully_connected = False
        self.data = {}

    def connected(self, uri):
        print(f'Connected to {uri}')

    def fully_connected(self, uri):
        print(f'Fully connected to {uri}')
        self.is_fully_connected = True

        # Reset the default observer
        self.cf.param.set_value('kalman.resetEstimation', 1)

        # Reset the ae483 observer
        self.cf.param.set_value('ae483par.reset_observer', 1)

        # Enable the controller (1 for default controller, 4 for ae483 controller)
        if self.use_controller:
            self.cf.param.set_value('stabilizer.controller', 4)
            self.cf.param.set_value('powerDist.motorSetEnable', 1)
        else:
            self.cf.param.set_value('stabilizer.controller', 1)
            self.cf.param.set_value('powerDist.motorSetEnable', 0)

        # Enable the observer (0 for disable, 1 for enable)
        if self.use_observer:
            self.cf.param.set_value('ae483par.use_observer', 1)
        else:
            self.cf.param.set_value('ae483par.use_observer', 0)

        # Start logging
        self.logconfs = []
        self.logconfs.append(LogConfig(name=f'LogConf0', period_in_ms=10))
        num_variables = 0
        for v in variables:
            num_variables += 1
            if num_variables > 5: # <-- could increase if you paid attention to types / sizes (max 30 bytes per packet)
                num_variables = 0
                self.logconfs.append(LogConfig(name=f'LogConf{len(self.logconfs)}', period_in_ms=10))
            self.data[v] = {'time': [], 'data': []}
            self.logconfs[-1].add_variable(v)
        for logconf in self.logconfs:
            try:
                self.cf.log.add_config(logconf)
                logconf.data_received_cb.add_callback(self.log_data)
                logconf.error_cb.add_callback(self.log_error)
                logconf.start()
            except KeyError as e:
                print(f'Could not start {logconf.name} because {e}')
                for v in logconf.variables:
                    print(f' - {v.name}')
            except AttributeError:
                print(f'Could not start {logconf.name} because of bad configuration')
                for v in logconf.variables:
                    print(f' - {v.name}')

    def connection_failed(self, uri, msg):
        print(f'Connection to {uri} failed: {msg}')

    def connection_lost(self, uri, msg):
        print(f'Connection to {uri} lost: {msg}')

    def disconnected(self, uri):
        print(f'Disconnected from {uri}')
        self.is_fully_connected = False

    def log_data(self, timestamp, data, logconf):
        for v in logconf.variables:
            self.data[v.name]['time'].append(timestamp)
            self.data[v.name]['data'].append(data[v.name])

    def log_error(self, logconf, msg):
        print(f'Error when logging {logconf}: {msg}')

    def move(self, x, y, z, yaw, dt):
        print(f'Move to {x}, {y}, {z} with yaw {yaw} degrees for {dt} seconds')
        start_time = time.time()
        while time.time() - start_time < dt:
            self.cf.commander.send_position_setpoint(x, y, z, yaw)
            time.sleep(0.1)

    def move_smooth(self, p1, p2, yaw, speed):
        print(f'Move smoothly from {p1} to {p2} with yaw {yaw} degrees at {speed} meters / second')
        p1 = np.array(p1)
        p2 = np.array(p2)

        # Compute distance from p1 to p2
        distance_from_p1_to_p2 = np.linalg.norm(p2-p1) # <-- FIXME (B)

        # Compute time it takes to move from p1 to p2 at desired speed
        time_from_p1_to_p2 = distance_from_p1_to_p2 / speed # <-- FIXME (C)

        start_time = time.time()
        while True:
            current_time = time.time()

            # Compute what fraction of the distance from p1 to p2 should have
            # been travelled by the current time
            s = (current_time - start_time) / time_from_p1_to_p2 # <-- FIXME (D)

            # Compute where the drone should be at the current time, in the
            # coordinates of the world frame
            p = (1-s) * p1 + s * p2 # <-- FIXME (E)

            self.cf.commander.send_position_setpoint(p[0], p[1], p[2], yaw)
            if s >= 1:
                return
            else:
                time.sleep(0.1)

    def stop(self, dt):
        print(f'Stop for {dt} seconds')
        self.cf.commander.send_stop_setpoint()
        start_time = time.time()
        while time.time() - start_time < dt:
            time.sleep(0.1)

    def disconnect(self):
        self.cf.close_link()

    def write_data(self, filename='logged_data.json'):
        with open(filename, 'w') as outfile:
            json.dump(self.data, outfile, indent=4, sort_keys=False)


def letter_move(char, x_pos, x_dim, z_dim):
  # convert letter to uppercase
  char = char.upper()

  # define some universal parameters
  yaw = 0.0
  dt = 0.2
  # speed = 2.0

  # define some location parameters
  x_left = 0.0*x_dim + x_pos
  x_mid = 0.5*x_dim + x_pos
  x_right = x_dim + x_pos
  # z_low = 0.5
  # z_mid = 0.5*z_dim + z_low
  # z_hi = z_dim + z_low

  if(char == 'A'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth( [x_left,          0.0, 0.5], [x_mid,           0.0, 1.0], yaw, dt)
    client.move_smooth( [x_mid,           0.0, 1.0], [x_right,         0.0, 0.5], yaw, dt)
    client.move_smooth( [x_right,         0.0, 0.5], [0.8*x_dim+x_pos, 0.0, 0.7], yaw, dt)
    client.move_smooth( [0.8*x_dim+x_pos, 0.0, 0.7], [0.4*x_dim+x_pos, 0.0, 0.7], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth( [0.4*x_dim+x_pos, 0.0, 0.7], [x_right,         0.0, 0.5], yaw, dt) #lr corner

  if(char == 'B'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth( [x_left,          0.0, 0.5], [x_left,          0.0, 1.0], yaw, dt)
    client.move_smooth( [x_left,          0.0, 1.0], [0.8*x_dim+x_pos, 0.0, 1.0], yaw, dt)
    client.move_smooth( [0.8*x_dim+x_pos, 0.0, 1.0], [0.8*x_dim+x_pos, 0.0, 0.5], yaw, dt)
    client.move_smooth( [0.8*x_dim+x_pos, 0.0, 0.5], [x_left,          0.0, 0.5], yaw, dt)
    client.move_smooth( [x_left,          0.0, 0.5], [x_left,          0.0, 0.8], yaw, dt)
    client.move_smooth( [x_left,          0.0, 0.8], [0.8*x_dim+x_pos, 0.0, 0.8], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth( [0.8*x_dim+x_pos, 0.0, 0.8], [x_right,         0.0, 0.5], yaw, dt) #lr corner

  if(char == 'C'):
    client.move_smooth( [x_left,  0.0, 0.5], [x_right, 0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth( [x_right, 0.0, 1.0], [x_left,  0.0, 1.0], yaw, dt)
    client.move_smooth( [x_left,  0.0, 1.0], [x_left,  0.0, 0.5], yaw, dt)
    client.move_smooth( [x_left,  0.0, 0.5], [x_right, 0.0, 0.5], yaw, dt) #lr corner
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off

  if(char == 'D'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5 ], [x_left,  0.0, 1.0 ], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0 ], [x_right, 0.0, 0.75], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.75], [x_left,  0.0, 0.5 ], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_left,  0.0, 0.5 ], [x_right, 0.0, 0.5 ], yaw, dt) #lr corner

  if(char == 'E'):
    client.move_smooth([x_left,  0.0, 0.5 ], [x_right, 0.0, 1.0 ], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_right, 0.0, 1.0 ], [x_left,  0.0, 1.0 ], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0 ], [x_left,  0.0, 0.5 ], yaw, dt)
    client.move_smooth([x_left,  0.0, 0.5 ], [x_right, 0.0, 0.5 ], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_right, 0.0, 0.5 ], [x_right, 0.0, 0.75], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_right, 0.0, 0.75], [x_left,  0.0, 0.75], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_left,  0.0, 0.75], [x_right, 0.0, 0.5 ], yaw, dt) #lr corner

  if(char == 'F'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5 ], [x_left,  0.0, 1.0 ], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0 ], [x_right, 0.0, 1.0 ], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_right, 0.0, 1.0 ], [x_right, 0.0, 0.75], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_right, 0.0, 0.75], [x_left,  0.0, 0.75], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_left,  0.0, 0.75], [x_right, 0.0, 0.5 ], yaw, dt) #lr corner

  if(char == 'G'):
    client.move_smooth([x_left,  0.0, 0.5 ], [x_right, 0.0, 1.0 ], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_right, 0.0, 1.0 ], [x_left,  0.0, 1.0 ], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0 ], [x_left,  0.0, 0.5 ], yaw, dt)
    client.move_smooth([x_left,  0.0, 0.5 ], [x_right, 0.0, 0.5 ], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.5 ], [x_right, 0.0, 0.75], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.75], [x_mid,   0.0, 0.75], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_mid,   0.0, 0.75], [x_right, 0.0, 0.5 ], yaw, dt) #lr corner

  if(char == 'H'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5 ], [x_left,  0.0, 1.0 ], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0 ], [x_left,  0.0, 0.75], yaw, dt)
    client.move_smooth([x_left,  0.0, 0.75], [x_right, 0.0, 0.75], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.75], [x_right, 0.0, 1.0 ], yaw, dt)
    client.move_smooth([x_right, 0.0, 1.0 ], [x_right, 0.0, 0.5 ], yaw, dt) #lr corner
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off

  if(char == 'I'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5], [x_left,  0.0, 0.5], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.5], [x_mid,   0.0, 0.5], yaw, dt)
    client.move_smooth([x_mid,   0.0, 0.5], [x_mid,   0.0, 1.0], yaw, dt)
    client.move_smooth([x_mid,   0.0, 1.0], [x_left,  0.0, 1.0], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0], [x_right, 0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_right, 0.0, 1.0], [x_right, 0.0, 0.5], yaw, dt) #lr corner

  if(char == 'J'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5], [x_mid,   0.0, 0.5], yaw, dt)
    client.move_smooth([x_mid,   0.0, 0.5], [x_mid,   0.0, 1.0], yaw, dt)
    client.move_smooth([x_mid,   0.0, 1.0], [x_left,  0.0, 1.0], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0], [x_right, 0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_right, 0.0, 1.0], [x_right, 0.0, 0.5], yaw, dt) #lr corner

  if(char == 'K'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5 ], [x_left,  0.0, 1.0 ], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_left,  0.0, 1.0 ], [x_right, 0.0, 1.0 ], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_right, 0.0, 1.0 ], [x_left,  0.0, 0.75], yaw, dt)
    client.move_smooth([x_left,  0.0, 0.75], [x_right, 0.0, 0.5 ], yaw, dt) #lr corner
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off

  if(char == 'L'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left, 0.0, 0.5], [x_left,  0.0, 1.0], yaw, dt)
    client.move_smooth([x_left, 0.0, 1.0], [x_left,  0.0, 0.5], yaw, dt)
    client.move_smooth([x_left, 0.0, 0.5], [x_right, 0.0, 0.5], yaw, dt) #lr corner
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off

  if(char == 'M'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5], [x_left,  0.0, 1.0], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0], [x_mid,   0.0, 0.5], yaw, dt)
    client.move_smooth([x_mid,   0.0, 0.5], [x_right, 0.0, 1.0], yaw, dt)
    client.move_smooth([x_right, 0.0, 1.0], [x_right, 0.0, 0.5], yaw, dt) #lr corner
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off

  if(char == 'N'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5], [x_left,  0.0, 1.0], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0], [x_right, 0.0, 0.5], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.5], [x_right, 0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_right, 0.0, 1.0], [x_right, 0.0, 0.5], yaw, dt) #lr corner

  if(char == 'O'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5], [x_left,  0.0, 1.0], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0], [x_right, 0.0, 1.0], yaw, dt)
    client.move_smooth([x_right, 0.0, 1.0], [x_right, 0.0, 0.5], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.5], [x_left,  0.0, 0.5], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_left,  0.0, 0.5], [x_right, 0.0, 0.5], yaw, dt) #lr corner
  
  if(char == 'P'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5 ], [x_left,  0.0, 1.0 ], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0 ], [x_right, 0.0, 1.0 ], yaw, dt)
    client.move_smooth([x_right, 0.0, 1.0 ], [x_right, 0.0, 0.75], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.75], [x_left,  0.0, 0.75], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_left,  0.0, 0.75], [x_right, 0.0, 0.5 ], yaw, dt) #lr corner
  
  if(char == 'Q'):
    client.move_smooth([x_left,          0.0, 0.5], [x_left,          0.0, 0.6], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,          0.0, 0.6], [x_left,          0.0, 1.0], yaw, dt)
    client.move_smooth([x_left,          0.0, 1.0], [0.8*x_dim+x_pos, 0.0, 1.0], yaw, dt)
    client.move_smooth([0.8*x_dim+x_pos, 0.0, 1.0], [0.8*x_dim+x_pos, 0.0, 0.6], yaw, dt)
    client.move_smooth([0.8*x_dim+x_pos, 0.0, 0.6], [x_left,          0.0, 0.6], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_left,          0.0, 0.6], [0.4*x_dim+x_pos, 0.0, 0.8], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([0.4*x_dim+x_pos, 0.0, 0.8], [x_right,         0.0, 0.5], yaw, dt) #lr corner
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
  
  if(char == 'R'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5 ], [x_left,  0.0, 1.0 ], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0 ], [x_right, 0.0, 1.0 ], yaw, dt)
    client.move_smooth([x_right, 0.0, 1.0 ], [x_right, 0.0, 0.75], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.75], [x_left,  0.0, 0.75], yaw, dt)
    client.move_smooth([x_left,  0.0, 0.75], [x_right, 0.0, 0.5 ], yaw, dt) #lr corner
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
  
  if(char == 'S'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5 ], [x_right, 0.0, 0.5 ], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.5 ], [x_right, 0.0, 0.75], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.75], [x_left,  0.0, 0.75], yaw, dt)
    client.move_smooth([x_left,  0.0, 0.75], [x_left,  0.0, 1.0 ], yaw, dt)
    client.move_smooth([x_left,  0.0, 1.0 ], [x_right, 0.0, 1.0 ], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_right, 0.0, 1.0 ], [x_right, 0.0, 0.5 ], yaw, dt) #lr corner
  
  if(char == 'T'):
    client.move_smooth([x_left,  0.0, 0.5], [x_left,  0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 1.0], [x_right, 0.0, 1.0], yaw, dt)
    client.move_smooth([x_right, 0.0, 1.0], [x_mid,   0.0, 1.0], yaw, dt)
    client.move_smooth([x_mid,   0.0, 1.0], [x_mid,   0.0, 0.5], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_mid,   0.0, 0.5], [x_right, 0.0, 0.5], yaw, dt) #lr corner
  
  if(char == 'U'):
    client.move_smooth([x_left,  0.0, 0.5], [x_left,  0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 1.0], [x_left,  0.0, 0.5], yaw, dt)
    client.move_smooth([x_left,  0.0, 0.5], [x_right, 0.0, 0.5], yaw, dt)
    client.move_smooth([x_right, 0.0, 0.5], [x_right, 0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_right, 0.0, 1.0], [x_right, 0.0, 0.5], yaw, dt) #lr corner
  
  if(char == 'V'):
    client.move_smooth([x_left,  0.0, 0.5], [x_left,  0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 1.0], [x_mid,   0.0, 0.5], yaw, dt)
    client.move_smooth([x_mid,   0.0, 0.5], [x_right, 0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_right, 0.0, 1.0], [x_right, 0.0, 0.5], yaw, dt) #lr corner
  
  if(char == 'W'):
    client.move_smooth([x_left,           0.0, 0.5], [x_left,           0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,           0.0, 1.0], [0.25*x_dim+x_pos, 0.0, 0.5], yaw, dt)
    client.move_smooth([0.25*x_dim+x_pos, 0.0, 0.5], [x_right,          0.0, 1.0], yaw, dt)
    client.move_smooth([x_right,          0.0, 1.0], [0.75*x_dim+x_pos, 0.0, 0.5], yaw, dt)
    client.move_smooth([0.75*x_dim+x_pos, 0.0, 0.5], [x_right,          0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_right,          0.0, 1.0], [x_right,          0.0, 0.5], yaw, dt) #lr corner
  
  if(char == 'X'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5], [x_right, 0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_right, 0.0, 1.0], [x_left,  0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 1.0], [x_right, 0.0, 0.5], yaw, dt) #lr corner
  
  if(char == 'Y'):
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 0.5 ], [x_right, 0.0, 1.0 ], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_right, 0.0, 1.0 ], [x_left,  0.0, 1.0 ], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 1.0 ], [x_mid,   0.0, 0.75], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off
    client.move_smooth([x_mid,   0.0, 0.75], [x_right, 0.0, 0.5 ], yaw, dt) #lr corner
  
  if(char == 'Z'):
    client.move_smooth([x_left,  0.0, 0.5], [x_left,  0.0, 1.0], yaw, dt)
    client.cf.param.set_value('ring.headlightEnable', 1) # Headlights on
    client.move_smooth([x_left,  0.0, 1.0], [x_right, 0.0, 1.0], yaw, dt)
    client.move_smooth([x_right, 0.0, 1.0], [x_left,  0.0, 0.5], yaw, dt)
    client.move_smooth([x_left,  0.0, 0.5], [x_right, 0.0, 0.5], yaw, dt) #lr corner 
    client.cf.param.set_value('ring.headlightEnable', 0) # Headlights off

if __name__ == '__main__':
    # Initialize everything
    logging.basicConfig(level=logging.ERROR)
    cflib.crtp.init_drivers()

    # Create and start the client that will connect to the drone
    client = SimpleClient(uri, use_controller=True, use_observer=False) # <-- FIXME
    while not client.is_fully_connected:
        time.sleep(0.1)

    # Allows lighthouse.x .y .z to be logged? 
    client.cf.param.set_value('lighthouse.method', 0)

    # [added for using the lighthouse] Allows the Kalman Filter to be used in the state estimation
    client.cf.param.set_value('stabilizer.estimator', 2)

    # Leave time at the start to initialize
    client.stop(1.0)

    # # Insert move commands here...
    print('hello world')

    # ## - take off and hover (with zero yaw)
    # client.move(0.0, 0.0, 0.15, 0.0, 1.0)
    # #client.move_smooth([0.0, 0.0, 0.15], [0.0, 0.0, 0.30], 0.0, 1)
    # client.move(0.0, 0.0, 0.30, 0.0, 10.0)
    # client.move(0.0, 0.0, 0.15, 0.0, 1.0)

    # ## Lab 6 Hover Test vvvvvvvvv
    # # Take off and hover (with zero yaw)
    # client.move(0.0, 0.0, 0.15, 0.0, 1.0)
    # client.move(0.0, 0.0, 0.30, 0.0, 1.0)
    
    # # Keep hovering (with zero yaw)
    # client.move(0.0, 0.0, 0.45, 0.0, 11.0)

    # # Go back to hover (with zero yaw) and prepare to land
    # client.move(0.0, 0.0, 0.30, 0.0, 1.0)
    # client.move(0.0, 0.0, 0.15, 0.0, 1.0)
    # ## Lab 6 Hover Test ^^^^^^^^^ 

  # # ## Lab 7 Square Test vvvvvvvvvv
  #   # Take off and hover (with zero yaw)
  #   client.move(0.0, 0.0, 0.15, 0.0, 1.0)
  #   client.move_smooth([0.0, 0.0, 0.15], [0.0, 0.0, 0.5], 0.0, 0.2)
  #   client.move(0.0, 0.0, 0.5, 0.0, 1.0)
  #   print("in hover")

  #  # Fly in a square
  #   client.move_smooth([0.0, 0.0, 0.5], [0.5, 0.0, 0.5], 0.0, 0.2)
  #   client.move(0.5, 0.0, 0.5, 0.0, 1.0)
  #   client.move_smooth([0.5, 0.0, 0.5], [0.5, 0.5, 0.5], 0.0, 0.2)
  #   client.move(0.5, 0.5, 0.5, 0.0, 1.0)
  #   client.move_smooth([0.5, 0.5, 0.5], [0.0, 0.5, 0.5], 0.0, 0.2)
  #   client.move(0.0, 0.5, 0.5, 0.0, 1.0)
  #   client.move_smooth([0.0, 0.5, 0.5], [0.0, 0.0, 0.5], 0.0, 0.2)
  #   print("finished square")

  #   # Go back to hover (with zero yaw) and prepare to land
  #   client.move(0.0, 0.0, 0.5, 0.0, 1.0)
  #   client.move_smooth([0.0, 0.0, 0.5], [0.0, 0.0, 0.15], 0.0, 0.2)
  #   client.move(0.0, 0.0, 0.15, 0.0, 1.0)
  #   print("land")

  # #   ## Lab 7 Square Test ^^^^^^^^^^


    # ## Lab 8 Flight Test vvvvvvvvvvvvvvvvv
    # # Take off and hover (with zero yaw)
    # client.move(0.0, 0.0, 0.15, 0.0, 1.0)
    # client.move_smooth([0.0, 0.0, 0.15], [0.0, 0.0, 0.5], 0.0, 0.2)
    # client.move(0.0, 0.0, 0.5, 0.0, 1.0)

    # # Fly in a square five times (with a pause at each corner)
    # num_squares = 5
    # for i in range(num_squares):
    #     client.move_smooth([0.0, 0.0, 0.5], [0.5, 0.0, 0.5], 0.0, 0.2)
    #     client.move(0.5, 0.0, 0.5, 0.0, 1.0)
    #     client.move_smooth([0.5, 0.0, 0.5], [0.5, 0.5, 0.5], 0.0, 0.2)
    #     client.move(0.5, 0.5, 0.5, 0.0, 1.0)
    #     client.move_smooth([0.5, 0.5, 0.5], [0.0, 0.5, 0.5], 0.0, 0.2)
    #     client.move(0.0, 0.5, 0.5, 0.0, 1.0)
    #     client.move_smooth([0.0, 0.5, 0.5], [0.0, 0.0, 0.5], 0.0, 0.2)
    #     client.move(0.0, 0.0, 0.5, 0.0, 1.0)
    
    # # Go back to hover (with zero yaw) and prepare to land
    # client.move_smooth([0.0, 0.0, 0.5], [0.0, 0.0, 0.15], 0.0, 0.2)
    # client.move(0.0, 0.0, 0.15, 0.0, 1.0)

    # ## Lab 8 Flight Test ^^^^^^^^^^^^^^^^^ 

    
    ## - FINAL PROJECT: Spell a word vvvvvvvvvvvvvvvvvvvv
    name_string = "NOOR" # input string

    #convert string to list of characters
    input_list = list(name_string)

    # define x-distance for each letter
    left_shift = 0.30

    # define z-distance for each letter
    vertical_shift = 0.30

    #start at x = starting_position
    starting_position = -1*left_shift * len(name_string) / 2 # in m
    iterator = starting_position # or just 0 
    
    drone_speed = 0.2 # in m/s

    # take off from origin and move to starting position 
    client.move_smooth([0, 0.0, 0.10], [iterator, 0.0, 0.30], 0.0, drone_speed)

    for i in input_list:
        letter_move(i, iterator, left_shift, vertical_shift)
        iterator = iterator+left_shift+0.1
        client.move(iterator, 0, 0.5, 0,2.0)

    #Return to origin to Land
    client.move_smooth([iterator, 0.0, 0.5], [iterator, 0.0, 0.15], 0.0, drone_speed)
    client.move_smooth([iterator, 0.0, 0.15], [0, 0.0, 0.15], 0.0, drone_speed)
    print('goodbye world')
    ## - FINAL PROJECT: Speall a word ^^^^^^^^^^^^^^^^^^^^^^^
    
    
    # Pause for a second
    client.stop(1.0)

    # Disconnect from drone
    client.disconnect()

    # Write data from flight
    # client.write_data('1206_default_everything_hover2.json')
    # client.write_data('1206_custom_everything_hover1.json')
    # client.write_data('1206_default_observer_hover5.json')
    client.write_data('NOOR_flight_5.json')
    # client.write_data('#####.json')
    
