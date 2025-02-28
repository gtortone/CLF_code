
# op codes
RD_REG = 0x03
WR_REG = 0x02

# SENSOR TYPES

# RTD
SENSOR_TYPE__RTD_PT_10 = 0b1010 << 27
SENSOR_TYPE__RTD_PT_50 = 0b1011 << 27
SENSOR_TYPE__RTD_PT_100 = 0b1100 << 27
SENSOR_TYPE__RTD_PT_200 = 0b1101 << 27
SENSOR_TYPE__RTD_PT_500 = 0b1110 << 27
SENSOR_TYPE__RTD_PT_1000 = 0b1111 << 27
SENSOR_TYPE__RTD_PT_1000_375 = 0b10000 << 27
SENSOR_TYPE__RTD_NI_120 = 0b10001 << 27
SENSOR_TYPE__RTD_CUSTOM = 0b10010 << 27

# sense resistor
SENSOR_TYPE__SENSE_RESISTOR = 0b11101 << 27
SENSOR_TYPE__NONE = 0b0 << 27

# direct ADC
SENSOR_TYPE__DIRECT_ADC = 0b11110 << 27

# thermistor
SENSOR_TYPE__THERMISTOR_44004_2P252K_25C = 0b10011 << 27
SENSOR_TYPE__THERMISTOR_44005_3K_25C = 0b10100 << 27
SENSOR_TYPE__THERMISTOR_44007_5K_25C = 0b10101 << 27
SENSOR_TYPE__THERMISTOR_44006_10K_25C = 0b10110 << 27
SENSOR_TYPE__THERMISTOR_44008_30K_25C = 0b10111 << 27
SENSOR_TYPE__THERMISTOR_YSI_400_2P252K_25C = 0b11000 << 27
SENSOR_TYPE__THERMISTOR_1003K_1K_25C = 0b11001 << 27
SENSOR_TYPE__THERMISTOR_CUSTOM_STEINHART_HART = 0b11010 << 27
SENSOR_TYPE__THERMISTOR_CUSTOM_TABLE = 0b11011 << 27

# thermocouple
SENSOR_TYPE__TYPE_J_THERMOCOUPLE = 0b1 << 27
SENSOR_TYPE__TYPE_K_THERMOCOUPLE = 0b10 << 27
SENSOR_TYPE__TYPE_E_THERMOCOUPLE = 0b11 << 27
SENSOR_TYPE__TYPE_N_THERMOCOUPLE = 0b100 << 27
SENSOR_TYPE__TYPE_R_THERMOCOUPLE = 0b101 << 27
SENSOR_TYPE__TYPE_S_THERMOCOUPLE = 0b110 << 27
SENSOR_TYPE__TYPE_T_THERMOCOUPLE = 0b111 << 27
SENSOR_TYPE__TYPE_B_THERMOCOUPLE = 0b1000 << 27
SENSOR_TYPE__CUSTOM_THERMOCOUPLE = 0b1001 << 27

# off-chip diode
SENSOR_TYPE__OFF_CHIP_DIODE = 0b11100 << 27

# RTD

# rtd - rsense channel
RTD_RSENSE_CHANNEL_LSB = 22
RTD_RSENSE_CHANNEL__NONE = 0b0 << 22
RTD_RSENSE_CHANNEL__1 = 0b1 << 22
RTD_RSENSE_CHANNEL__2 = 0b10 << 22
RTD_RSENSE_CHANNEL__3 = 0b11 << 22
RTD_RSENSE_CHANNEL__4 = 0b100 << 22
RTD_RSENSE_CHANNEL__5 = 0b101 << 22
RTD_RSENSE_CHANNEL__6 = 0b110 << 22
RTD_RSENSE_CHANNEL__7 = 0b111 << 22
RTD_RSENSE_CHANNEL__8 = 0b1000 << 22
RTD_RSENSE_CHANNEL__9 = 0b1001 << 22
RTD_RSENSE_CHANNEL__10 = 0b1010 << 22
RTD_RSENSE_CHANNEL__11 = 0b1011 << 22
RTD_RSENSE_CHANNEL__12 = 0b1100 << 22
RTD_RSENSE_CHANNEL__13 = 0b1101 << 22
RTD_RSENSE_CHANNEL__14 = 0b1110 << 22
RTD_RSENSE_CHANNEL__15 = 0b1111 << 22
RTD_RSENSE_CHANNEL__16 = 0b10000 << 22
RTD_RSENSE_CHANNEL__17 = 0b10001 << 22
RTD_RSENSE_CHANNEL__18 = 0b10010 << 22
RTD_RSENSE_CHANNEL__19 = 0b10011 << 22
RTD_RSENSE_CHANNEL__20 = 0b10100 << 22

# rtd - num wires
RTD_NUM_WIRES_LSB = 20
RTD_NUM_WIRES__2_WIRE = 0b0 << 20
RTD_NUM_WIRES__3_WIRE = 0b1 << 20
RTD_NUM_WIRES__4_WIRE = 0b10 << 20
RTD_NUM_WIRES__4_WIRE_KELVIN_RSENSE = 0b11 << 20

# rtd - excitation mode
RTD_EXCITATION_MODE_LSB = 18
RTD_EXCITATION_MODE__NO_ROTATION_NO_SHARING = 0b0 << 18
RTD_EXCITATION_MODE__NO_ROTATION_SHARING = 0b1 << 18
RTD_EXCITATION_MODE__ROTATION_SHARING = 0b10 << 18

# rtd - excitation current
RTD_EXCITATION_CURRENT_LSB = 14
RTD_EXCITATION_CURRENT__EXTERNAL = 0b0 << 14
RTD_EXCITATION_CURRENT__5UA = 0b1 << 14
RTD_EXCITATION_CURRENT__10UA = 0b10 << 14
RTD_EXCITATION_CURRENT__25UA = 0b11 << 14
RTD_EXCITATION_CURRENT__50UA = 0b100 << 14
RTD_EXCITATION_CURRENT__100UA = 0b101 << 14
RTD_EXCITATION_CURRENT__250UA = 0b110 << 14
RTD_EXCITATION_CURRENT__500UA = 0b111 << 14
RTD_EXCITATION_CURRENT__1MA = 0b1000 << 14

# rtd - standard
RTD_STANDARD_LSB = 12
RTD_STANDARD__EUROPEAN = 0b0 << 12
RTD_STANDARD__AMERICAN = 0b1 << 12
RTD_STANDARD__JAPANESE = 0b10 << 12
RTD_STANDARD__ITS_90 = 0b11 << 12

# rtd - custom address
RTD_CUSTOM_ADDRESS_LSB = 6

# rtd - custom length-1
RTD_CUSTOM_LENGTH_1_LSB = 0

# rtd - custom values
RTD_CUSTOM_VALUES_LSB = 31

# sense resistor

# sense resistor - value
SENSE_RESISTOR_VALUE_LSB = 0

# direct ADC

# direct ADC - differential
DIRECT_ADC_DIFFERENTIAL_LSB = 26
DIRECT_ADC_DIFFERENTIAL = 0b0 << 26
DIRECT_ADC_SINGLE_ENDED = 0b1 << 26

# thermistor

# thermistor - rsense channel
THERMISTOR_RSENSE_CHANNEL_LSB = 22
THERMISTOR_RSENSE_CHANNEL__NONE = 0b0 << 22
THERMISTOR_RSENSE_CHANNEL__1 = 0b1 << 22
THERMISTOR_RSENSE_CHANNEL__2 = 0b10 << 22
THERMISTOR_RSENSE_CHANNEL__3 = 0b11 << 22
THERMISTOR_RSENSE_CHANNEL__4 = 0b100 << 22
THERMISTOR_RSENSE_CHANNEL__5 = 0b101 << 22
THERMISTOR_RSENSE_CHANNEL__6 = 0b110 << 22
THERMISTOR_RSENSE_CHANNEL__7 = 0b111 << 22
THERMISTOR_RSENSE_CHANNEL__8 = 0b1000 << 22
THERMISTOR_RSENSE_CHANNEL__9 = 0b1001 << 22
THERMISTOR_RSENSE_CHANNEL__10 = 0b1010 << 22
THERMISTOR_RSENSE_CHANNEL__11 = 0b1011 << 22
THERMISTOR_RSENSE_CHANNEL__12 = 0b1100 << 22
THERMISTOR_RSENSE_CHANNEL__13 = 0b1101 << 22
THERMISTOR_RSENSE_CHANNEL__14 = 0b1110 << 22
THERMISTOR_RSENSE_CHANNEL__15 = 0b1111 << 22
THERMISTOR_RSENSE_CHANNEL__16 = 0b10000 << 22
THERMISTOR_RSENSE_CHANNEL__17 = 0b10001 << 22
THERMISTOR_RSENSE_CHANNEL__18 = 0b10010 << 22
THERMISTOR_RSENSE_CHANNEL__19 = 0b10011 << 22
THERMISTOR_RSENSE_CHANNEL__20 = 0b10100 << 22

# thermistor - differential
THERMISTOR_DIFFERENTIAL_LSB = 21
THERMISTOR_DIFFERENTIAL = 0b0 << 21
THERMISTOR_SINGLE_ENDED = 0b1 << 21

# thermistor - excitation mode
THERMISTOR_EXCITATION_MODE_LSB = 19
THERMISTOR_EXCITATION_MODE__NO_SHARING_NO_ROTATION = 0b0 << 19
THERMISTOR_EXCITATION_MODE__SHARING_ROTATION = 0b1 << 19
THERMISTOR_EXCITATION_MODE__SHARING_NO_ROTATION = 0b10 << 19

# thermistor - excitation current
THERMISTOR_EXCITATION_CURRENT_LSB = 15
THERMISTOR_EXCITATION_CURRENT__100NA = 0b0 << 15
THERMISTOR_EXCITATION_CURRENT__250NA = 0b1 << 15
THERMISTOR_EXCITATION_CURRENT__500NA = 0b10 << 15
THERMISTOR_EXCITATION_CURRENT__1UA = 0b11 << 15
THERMISTOR_EXCITATION_CURRENT__5UA = 0b100 << 15
THERMISTOR_EXCITATION_CURRENT__10UA = 0b101 << 15
THERMISTOR_EXCITATION_CURRENT__25UA = 0b110 << 15
THERMISTOR_EXCITATION_CURRENT__50UA = 0b111 << 15
THERMISTOR_EXCITATION_CURRENT__100UA = 0b1000 << 15
THERMISTOR_EXCITATION_CURRENT__250UA = 0b1001 << 15
THERMISTOR_EXCITATION_CURRENT__500UA = 0b1010 << 15
THERMISTOR_EXCITATION_CURRENT__1MA = 0b1011 << 15
THERMISTOR_EXCITATION_CURRENT__AUTORANGE = 0b1100 << 15
THERMISTOR_EXCITATION_CURRENT__INVALID_SETTING1 = 0b1101 << 15
THERMISTOR_EXCITATION_CURRENT__INVALID_SETTING2 = 0b1110 << 15
THERMISTOR_EXCITATION_CURRENT__EXTERNAL = 0b1111 << 15

# thermistor - custom address
THERMISTOR_CUSTOM_ADDRESS_LSB = 6

# thermistor - custom length-1
THERMISTOR_CUSTOM_LENGTH_1_LSB = 0

# thermistor - custom values
THERMISTOR_CUSTOM_VALUES_LSB = 31

# thermocouple

# tc - cold junction ch
TC_COLD_JUNCTION_CH_LSB = 22
TC_COLD_JUNCTION_CH__NONE = 0b0 << 22
TC_COLD_JUNCTION_CH__1 = 0b1 << 22
TC_COLD_JUNCTION_CH__2 = 0b10 << 22
TC_COLD_JUNCTION_CH__3 = 0b11 << 22
TC_COLD_JUNCTION_CH__4 = 0b100 << 22
TC_COLD_JUNCTION_CH__5 = 0b101 << 22
TC_COLD_JUNCTION_CH__6 = 0b110 << 22
TC_COLD_JUNCTION_CH__7 = 0b111 << 22
TC_COLD_JUNCTION_CH__8 = 0b1000 << 22
TC_COLD_JUNCTION_CH__9 = 0b1001 << 22
TC_COLD_JUNCTION_CH__10 = 0b1010 << 22
TC_COLD_JUNCTION_CH__11 = 0b1011 << 22
TC_COLD_JUNCTION_CH__12 = 0b1100 << 22
TC_COLD_JUNCTION_CH__13 = 0b1101 << 22
TC_COLD_JUNCTION_CH__14 = 0b1110 << 22
TC_COLD_JUNCTION_CH__15 = 0b1111 << 22
TC_COLD_JUNCTION_CH__16 = 0b10000 << 22
TC_COLD_JUNCTION_CH__17 = 0b10001 << 22
TC_COLD_JUNCTION_CH__18 = 0b10010 << 22
TC_COLD_JUNCTION_CH__19 = 0b10011 << 22
TC_COLD_JUNCTION_CH__20 = 0b10100 << 22

# tc - differential?
TC_DIFFERENTIAL_LSB = 21
TC_DIFFERENTIAL = 0b0 << 21
TC_SINGLE_ENDED = 0b1 << 21

# tc - open ckt detect
TC_OPEN_CKT_DETECT_LSB = 20
TC_OPEN_CKT_DETECT__NO = 0b0 << 20
TC_OPEN_CKT_DETECT__YES = 0b1 << 20

# tc - open ckt detect current
TC_OPEN_CKT_DETECT_CURRENT_LSB = 18
TC_OPEN_CKT_DETECT_CURRENT__10UA = 0b0 << 18
TC_OPEN_CKT_DETECT_CURRENT__100UA = 0b1 << 18
TC_OPEN_CKT_DETECT_CURRENT__500UA = 0b10 << 18
TC_OPEN_CKT_DETECT_CURRENT__1MA = 0b11 << 18

# tc - custom address
TC_CUSTOM_ADDRESS_LSB = 6

# tc - custom length-1
TC_CUSTOM_LENGTH_1_LSB = 0

# tc - custom values
TC_CUSTOM_VALUES_LSB = 31

# off-chip diode

# diode - differential
DIODE_DIFFERENTIAL_LSB = 26
DIODE_DIFFERENTIAL = 0b0 << 26
DIODE_SINGLE_ENDED = 0b1 << 26

# diode - num readings
DIODE_NUM_READINGS_LSB = 25
DIODE_NUM_READINGS__2 = 0b0 << 25
DIODE_NUM_READINGS__3 = 0b1 << 25

# diode - averaging on?
DIODE_AVERAGING_ON_LSB = 24
DIODE_AVERAGING_OFF = 0b0 << 24
DIODE_AVERAGING_ON = 0b1 << 24

# diode - current
DIODE_CURRENT_LSB = 22
DIODE_CURRENT__10UA_40UA_80UA = 0b0 << 22
DIODE_CURRENT__20UA_80UA_160UA = 0b1 << 22
DIODE_CURRENT__40UA_160UA_320UA = 0b10 << 22
DIODE_CURRENT__80UA_320UA_640UA = 0b11 << 22

# diode - ideality factor(eta)
DIODE_IDEALITY_FACTOR_LSB = 0

# global configuration constants
REJECTION__50_60_HZ = 0b00000000
REJECTION__60_HZ    = 0b00000001
REJECTION__50_HZ    = 0b00000010
TEMP_UNIT__C        = 0b00000000
TEMP_UNIT__F        = 0b00000100

# status byte constants
SENSOR_HARD_FAILURE = 0b10000000
ADC_HARD_FAILURE    = 0b01000000
CJ_HARD_FAILURE     = 0b00100000
CJ_SOFT_FAILURE     = 0b00010000
SENSOR_ABOVE        = 0b00001000
SENSOR_BELOW        = 0b00000100
ADC_RANGE_ERROR     = 0b00000010
VALID               = 0b00000001

# addresses
VOUT_CH_BASE    = 0x060
READ_CH_BASE    = 0x010
MULCONV_REG	    = 0x0F4


