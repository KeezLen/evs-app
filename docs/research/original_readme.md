Source: https://drive.google.com/file/d/1LOl6DZ8eArAG-pvjJ0M0ymrI0qznOHBl/view
Retrieved: 2026-11-18

*** Energy consumption data of the GridFlex Heeten project ***
Authors: V.M.J.J. Reijnders, M.E.T. Gerards, J.L. Hurink
Groups: Mathematics of Operations Research, Faculty of Electrical Engineering, Mathematics and Computer Science, University of Twente &
Computer Architecture for Embedded Systems, Faculty of Electrical Engineering, Mathematics and Computer Science, University of Twente

Contact information:

J.L. Hurink (j.l.hurink@utwente.nl)
University of Twente - Faculty of Electrical Engineering, Mathematics and Computer Science - Zilverling 4042
P.O. Box 217
7500 AE Enschede
The Netherlands

*** General information ***
The data in this dataset was collected during the GridFlex Heeten project (supported by the Dutch organization RVO under TEUE116230), as part of Victor Reijnders' PhD project. It is made available publically (though non-commercially) both as supplementary data for publication and the PhD thesis of Victor Reijnders, as well as to serve as data for other researchers to use.
The data was collected between August 2018 and August 2020 in 77 households all situated in Heeten (The Netherlands) and consists of electricity consumption and gas usage per minute per household. All participating households specified their data could be used in further research and the data of this project was collected in accordance with a privacy-by-design approach.

*** Measurement equipment ***
The data in this dataset was collected by installing an energy management system (EMS) in each household provided by ICT Group. These EMS were connected to the P4 port on the smart meter and read out the consumption data once per minute. 
Furthermore, if a battery was present, the battery management system was separately connected to the EMS. Also, if a PV system was present, a pulse meter was installed and connected to the EMS to separately measure the output.
All this data was then send over Wi-Fi to a cloud. The participants used an app to view their own energy consumption.

*** Data disclaimers ***
The collected energy data is often incomplete. This is due to several reasons. Firstly, as the household data is sent to the database via an internet connection, and this communication may fail due to internet outages or inhabitants turning off their router, data points may be missing for that household. Secondly, as (the internet connection of) the database server may be disrupted, also gaps in data of all households may occur. Thirdly, also the data the EMS reads from the smart meter may contain errors. These values have been mostly filtered out, though especially in the TOTAL_KWH some extreme jumps (>10 kWh in a minute) may be visible. These should be discarded.
The missing datapoints are not present in the dataset (also not as i.e. NaN or 0 values). These gaps, when only for short periods, can be easily solved using a linear filling method.
Another point to note is that a few households have a PV system installed, but no pulse meter. In these cases the UNC_KW cannot exclude the power output of the PV system from that of the complete household, so the values of UNC_KW of those households are not comparable to the other UNC_KW series.
Moreover, a few of the measurements state that the value is inaccurate to some degree. Nevertheless, their values are still provided for completeness.
Lastly, these are some starting points for using this data: TOTAL_KW gives the electricity consumption profile of a complete household (averaged per minute), and UNC_KW gives the same, but minus the battery and PV system, so it is only the electricity usage of the household devices.


*** Dataset explanation ***
The data in this dataset is subdivided as a value per house, per appliance-group, per measurement type, per time interval. These subdivision are explained further:

"house":
HouseX    : The household identifier, with X ranging from 1 to 77.
HouseTest : A dummy household provided by ICT Group to test if the connection is working.

"appliance":
SMARTMETER : Contains the measurements related to the smart meter, so the complete household.
PVMETER    : Contains the measurements related to the PV system (not available in all households).
BATTERY    : Contains the measurements related to the battery system (not available in all households).

"measurement":
BATTERY_EXPORT_KW   : Total energy the battery discharged since it was connected to the system, in kWh.
BATTERY_IMPORT_KW   : Total energy the battery charged since the battery was connected to the system, in kWh.
BATTERY_KW          : Average power output of the battery in the last minute (negative means charging), in kW.
BATTERY_TARGET_KW   : The requested power output of the battery, in kW.
BATTERY_TARGET_MODE : Optimization strategy of the battery, where 0 = local, so the battery tries to match BATTERY_TARGET_KW to BATTERY_KW, 1 = household, so the battery tries to steer BATTERY_KW such that TOTAL_KW matches BATTERY_TARGET_KW, 2 = failsafe, so the battery charges to a safe State of Charge (SoC) regardless of BATTERY_TARGET_KW
CHARGE_MODE         : Indicates the mode of battery which dictates what the battery can do, where 0 = battery is idle, 1 = battery can only charge, 2 = battery can only discharge, 3 = battery can do both.
CURRENT_PHASE_1     : Household current on phase 1, in A. Value is very inaccurate, but can be used to identify the phase the household is connected to.
CURRENT_PHASE_2     : Household current on phase 2, in A. Value is very inaccurate, but can be used to identify the phase the household is connected to.
CURRENT_PHASE_3     : Household current on phase 3, in A. Value is very inaccurate, but can be used to identify the phase the household is connected to.
EXPORT_KW           : Average power output of the household in the last minute (difference of consecutive measurements of EXPORT_KWH), in kW.
EXPORT_KWH          : Total energy the household has exported since the household was connected to the smart meter, in kWh.
GAS_USAGE_M3        : Total cubic meters of gas used since it was connected to the smart meter, in m3.
IMPORT_KW           : Average power input of the household in the last minute (difference of consecutive measurements of IMPORT_KWH), in kW.
IMPORT_KWH          : Total energy the household has imported since the household was connected to the smart meter, in kWh.
MAX_BATTERY_KW      : Discharge limit of the battery, so the maximum value BATTERY_KW is allowed to attain, in kW.
MIN_BATTERY_KW      : Charge limit of the battery, so the minimum value BATTERY_KW is allowed to attain, in kW.
MOMENTARY_EXPORT_KW : Power output from the household at the exact time of the measurement, in kW. Value is slightly inaccurate.
MOMENTARY_IMPORT_KW : Power input from the household at the exact time of the measurement, in kW. Value is slightly inaccurate.
MOMENTARY_PV_KW     : Power output from the PV system at the exact time of the measurement, in kW. Value is slightly inaccurate.
OPERATIONAL_STATE   : Indicates what the battery did do where 0 = battery was idle, 1 =  battery was charging, 2 = battery was discharging, 3 = battery had an error.
PV_KW               : Average power production of the PV system in the last minute (difference of consecutive measurements of PV_KWH), in kW.
PV_KWH              : Total energy produced by the PV system since the PV system was connected to the pulse meter, in kWh.
REQ_CHARGE_MODE     : The CHARGE_MODE that was requested from the battery.
STATE_OF_CHARGE     : The state of charge of the battery as a percentage of the capacity. Value is extremely inaccurate.
TOTAL_KW            : Average power usage of the household in the last minute (neg. means exporting power, difference of consecutive measurements of TOTAL_KWH), in kW.
TOTAL_KWH           : Total energy the household has used since the household was connected to the smart meter (neg. means exported energy, difference of EXPORT_KWH and IMPORT_KWH), in kWh.
UNC_KW              : Average power usage of the household excluding PV and battery in the last minute, in kW.

"time": 
YYYY-MM-DDThh:mm:ssZ: one-minute time interval (PT1m/YYYY-MM-DDThh:mm:ssZ) at the end of which the measurement value is taken, denoted in ISO 8061 (second precision), ranges from 2018-08-01T01:59:00+02:00 to 2020-08-31T23:58:00+02:00. Note that this date is denoted in local time, so CET (or CEST), taking Daylight Saving Time into account.

"value":
X : The value of the measurement (unit indicated in the measurement explanation)

*** Licence ***
This data is shared under the Attribution-NonCommercial-ShareAlike (CC BY-NC-SA) Licence. Before distributing or sharing (remixes, tweaks or transforms of) this data, please consult the contact person of this dataset.
