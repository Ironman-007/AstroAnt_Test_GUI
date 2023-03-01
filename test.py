# Central Command Tests
def test_cs_ping():
    return True

def test_cs_garage_open():
    return True

def test_cs_rover_not_turning():
    return True

def test_cs_rover_will_turn():
    return True

def test_cs_ping():
    return True

def test_cs_unused():
    return True

def test_cs_enter_dfu():
    return True

def test_cs_update_ant():
    return True

def test_cs_update_ant_fw_packet():
    return True


# Ant Command Tests
def test_ant_ping():
    return True

def test_ant_start():
    return True

def test_ant_calibrate():
    return True

def test_ant_ota():
    return True

def test_ant_off():
    return True

def test_ant_heater_on():
    return True

def test_ant_heater_off():
    return True

def test_ant_move_fwd():
    return True

def test_ant_move_bwd():
    return True

# utility
def connect_central():
    pass

def send_command():
    pass # TODO: send command to central via serial

def print_test_result(test_name, result):
    print(test_name + ": " + "Succeeded" if result else "Failed")

print("Connecting central station ...")
connect_central()
print("Connected to central station.")

success = test_cs_ping()
print_test_result("test_cs_ping", success)

success = test_cs_garage_open()
print_test_result("test_cs_garage_open", success)

success = test_cs_rover_not_turning()
print_test_result("test_cs_rover_not_turning", success)

success = test_cs_rover_will_turn()
print_test_result("test_cs_rover_will_turn", success)

success = test_cs_ping()
print_test_result("test_cs_ping", success)

success = test_cs_unused()
print_test_result("test_cs_unused", success)

success = test_cs_enter_dfu()
print_test_result("test_cs_enter_dfu", success)

success = test_cs_update_ant()
print_test_result("test_cs_update_ant", success)

success = test_cs_update_ant_fw_packet()
print_test_result("test_cs_update_ant_fw_packet", success)

success = test_ant_ping()
print_test_result("test_ant_ping", success)

success = test_ant_start()
print_test_result("test_ant_start", success)

success = test_ant_calibrate()
print_test_result("test_ant_calibrate", success)

success = test_ant_ota()
print_test_result("test_ant_ota", success)

success = test_ant_heater_on()
print_test_result("test_ant_heater_on", success)

success = test_ant_heater_off()
print_test_result("test_ant_heater_off", success)

success = test_ant_move_fwd()
print_test_result("test_ant_move_fwd", success)

success = test_ant_move_bwd()
print_test_result("test_ant_move_bwd", success)

success = test_ant_off()
print_test_result("test_ant_off", success)

# todo: verify command is ignored if not intact
# todo: verify heater works in bootloader
# todo: verify watchdog
