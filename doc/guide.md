# Guide
## Connection to wifi network
Use `ESP Config` wechat miniprogram or `EspBlufi` application to connect esp32 module to network

***Note: esp32 and HA should be in same network***

## Configure broker
Add a new user to your broker

```
username: maybetaken
password: maybetaken
```

***Note: This new user and password is mandatory***

## Install this integration
You can either
* Download this integration from HACS store 

or

* Copy the release version and unzip it to your config folder

## Add a new device
Input `Serial number` provided by vendor

## Appendix:
MakeSkyblue iotrix coexist verison

### Topics:
#### From module to HA
`<serial number>/makeskyblue/iotrix/notify`

#### From HA to module
`<serial number>/makeskyblue/iotrix/control/cmd`

### Data format:
#### From module to HA
`<slave id><read command><start address H><start address L><register number H><register number L><payload data>
`

e.g.
`01030064000211112222`
```
01: slave id
03: read command
00: start address H
64: start address L
00: register number H
02: register number L
1111: register 100 value
2222: register 101 value
```

#### From HA to module
`<slave id><write command><start address H><start address L><value H><value L>
`

e.g.
`010600000002`

```
01: slave id
03: write command
00: start address H
00: start address L
00: value H
02: value L
```

***Notice:This command sets work mode to SBU mode***
