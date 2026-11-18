Source: https://docs.google.com/document/d/13bGsmuVKPGhKspC5-eJKWolf-fCDga29/edit
Retrieved: 2026-11-18

Note: A few additional datasets have been added at the bottom of the document (shown in grey).
This dataset appears particularly relevant.

https://ideas.repec.org/a/eee/jbrese/v106y2020icp377-387.html#:~:text=186(PB).%20*%20H%C3%B6llig%2C%20Christoph%20E.%20%26%20Tumasjan%2C,Consumer%20Services%2C%20Elsevier%2C%20vol.%2050(C)%2C%20pages%20122%2D130.
Potential data sources for the model
P4 data
Weather
Calendar information (day of the week and public holidays)
Building characteristics
Heating systems
+ User information
P4 data consists of electricity consumption measured in kWh at 15-minute intervals and gas consumption measured in m³ hourly.
Similar applications for reference:
https://www.homewizard.com/?default=true
https://energysaverapp.com/
https://github.com/sokistar24/ecohome-energy-agent
Care-Based Eco-Feedback Augmented with Generative AI: Fostering Pro-Environmental Behavior through Emotional Attachment
AI-driven household electricity load forecasting: challenges, methods, and future directions
Energy-saving tips from Milieu Centraal:milieucentraal.nl
https://www.milieucentraal.nl/energie-besparen/snelle-bespaartips
Investigate how a household's energy consumption responds to weather conditions.
Data
Link
Stuff
The data in this dataset was collected during the GridFlex Heeten project, as part of Victor Reijnders' PhD project.The data was collected between August 2018 and August 2020 in 77 households all situated in Heeten (The Netherlands) and consists of electricity consumption and gas usage per minute per household. All participating households specified their anonymous data could be used in further research. The data of this project was collected in accordance with a privacy-by-design approach. 
https://data.4tu.nl/articles/_/14447257/1

The source information is in Dutch and may require translation.
Explanatory Notes for “Zonnedael” Datasets

August 25, 2014

This dataset contains actual consumption data from approximately 80 addresses, with time intervals of 15 minutes for electricity and 60 minutes for gas.

The data originates from smart meters for which the users gave consent to read and use the measurement data for research purposes.

The units of data are Wh/15min and m³/hr. Where data was missing or unrealistic, it has been corrected. Consequently, during certain periods, the data may display an average rather than actual consumption.

Some consumption series have been removed entirely because they were incomplete and/or contained unrealistic values.

Electricity and gas data can be linked to household type, housing type, and building age for each connection using the anonymous label 'Klant #' (Customer #) and the file "Klanttypering" (Customer Typology).

The measurement period for electricity runs from May 1, 2012, to March 7, 2014; for gas, it runs from May 1, 2012, to January 7, 2014.

Timestamps reflect local Dutch time (including Daylight Saving Time / Summer and Winter time).

https://www.liander.nl/over-ons/open-data
Or 
https://huggingface.co/datasets/OpenSynth/TUDelft-Electricity-Consumption-1.0
The IDEAL Household Energy Dataset comprises data from 255 UK homes. Alongside electric and gas data from each home the corpus contains individual room temperature and humidity readings and temperature readings from the boiler. For 39 of the 255 homes more detailed data is available, including individual electrical appliance use data, and data on individual radiators. Sensor data is augmented by anonymised survey data and metadata including occupant demographics, self-reported energy awareness and attitudes, and building, room and appliance characteristics.  

https://datashare.ed.ac.uk/items/15e82917-56ed-4282-99ef-7f211bf87f9d

Download time: approximately 20 hours.
Potentially useful for model training. Sensor selection should be considered carefully. The dataset includes real-time data from several types of household sensors.
The source information is in Dutch and may require translation.

1. Insight into Granted Energy Subsidies to Homeowners in the Netherlands by Street, Neighborhood, or Municipality Information on energy subsidies (such as ISDE) awarded to homeowners in the Netherlands, detailed at the street, neighborhood, or municipality level.
2. Insight into Energy Consumption by Homeowners in the Netherlands by Street, Neighborhood, or Municipality Information on electricity and gas consumption by homeowners in the Netherlands, detailed at the street, neighborhood, or municipality level.
3. Insight into Energy Performance Certificates (EPC) / Energy Labels of Homeowners in the Netherlands by Street, Neighborhood, or Municipality Information on energy labels (energielabels) assigned to homes in the Netherlands, detailed at the street, neighborhood, or municipality level.

data.overheid.nl

https://data.overheid.nl/community/datarequest/energie-in-nederland

The portal links to the following dataset:
https://opendata.cbs.nl/dataportaal/portal.html#/CBS/nl/dataset/table?graphtype=Table&tableId=81528NED
The portal provides a substantial amount of data, although much of it concerns the broader national picture. It may be useful for establishing reference values for households.

https://opendata.cbs.nl/#/CBS/nl/dataset/85140NED/table?ts=1790332391004

https://opendata.cbs.nl/#/CBS/nl/dataset/81528NED/table?ts=1790332419677

https://opendata.cbs.nl/#/CBS/nl/dataset/84948NED/table?ts=1790332469267https://opendata.cbs.nl/dataportaal/portal.html#/CBS/nl/dataset/table?graphtype=Table&tableId=81528NEDhttps://opendata.cbs.nl/#/CBS/nl/dataset/85140NED/table?ts=1790332391004https://opendata.cbs.nl/#/CBS/nl/dataset/81528NED/table?ts=1790332419677https://opendata.cbs.nl/#/CBS/nl/dataset/84948NED/table?ts=1790332469267
This table provides regional data on the average energy consumption per dwelling (natural gas and electricity) for private residential properties, broken down by housing type and ownership type across all neighborhoods (wijken) and sub-neighborhoods (buurten) in the Netherlands, as well as for the Netherlands as a whole. Additionally, the percentage of district heating is included strictly for total housing figures, as this is essential for accurately interpreting average natural gas consumption.

This dataset may be useful for comparing a user's consumption with that of nearby households and identifying whether it is above average. It may also provide a temporary reference point for new users, before sufficient P4 predictions are available.
https://www.cbs.nl/nl-nl/cijfers/detail/85999NED

This table contains data on average household energy consumption (natural gas and electricity), categorized by building type, construction year period, surface area class, presence of solar power systems, and household size for all private dwellings in the Netherlands, as well as specifically for gas-heated dwellings (individual central heating and shared/block heating).
For electricity, shared connections used for common facilities (such as elevators and hallway lighting in apartment buildings) cannot be allocated to individual units. These shared electricity deliveries are therefore excluded from the figures.
This dataset may be more suitable because it allows households similar to users to be selected, provided the relevant user information is available.
https://www.cbs.nl/nl-nl/cijfers/detail/85140NED

This table provides regional data on average household energy consumption (natural gas and electricity) for private dwellings, broken down by housing type and ownership type across the Netherlands as a whole, parts of the country (landsdelen), provinces, and municipalities. Additionally, the percentage of district heating is included strictly for total housing figures, as this is essential for accurately interpreting average natural gas consumption.

https://www.cbs.nl/nl-nl/cijfers/detail/81528NED

The data consists of BAG buildings (BAG-panden), a subset of BAG data for these buildings, and the accommodation units (verblijfsobjecten) located within them. Berths (ligplaatsen) and pitches (standplaatsen) are also included alongside a subset of BAG data.

Potentially useful for building-related information.
https://www.pdok.nl/introductie/-/article/basisregistratie-adressen-en-gebouwen-ba-1

Weather data
https://dataplatform.knmi.nl/

Potential application: understanding the CO₂ emissions associated with different energy sources. The relevance to the project remains to be established.
The table below shows CO2 emission factors of the production of electricity from specific energy sources. Electricity use does not cause direct emissions (Tank to Wheel) for the users of the electricity. The factors for emissions from electricity production are:
Production emissions of power plant: CO2 emissions in the production of electricity in the power plant.
Chain emissions production energy carriers: The CO2 emissions in the production of the energy carriers that the power plant uses.
Total: The sum of direct emissions when using the electricity (0) and the above production and chain emissions; the ‘well-to-wheel’ (WTW) emissions.
Infrastructure: The CO2 emissions from the construction and demolition of the energy production means (central, windmill, solar panel) per kWh generated (LCA approach).
The figures include transmission and distribution losses (T&D losses) of 4.06%.

https://co2emissiefactoren.nl/factoren/2026/11/elektriciteit/

Appliance-by-appliance and whole-home power demand for 5 UK homes recorded approximately once every 6s. Each appliance has a separate time series file channel_nn.dat and most have a channel_nn_button_press.dat file indicating switching events. This data set includes and extends UK-DALE-2015 disaggregated. 
https://ukerc.rl.ac.uk/cgi-bin/dataDiscover.pl?Action=detail&dataid=7d78f943-f9fe-413b-af52-1816f9d968b0

The REFIT Electrical Load Measurements dataset includes cleaned electrical consumption data in Watts for 20 households at aggregate and appliance level, timestamped and sampled at 8 second intervals. This dataset is intended to be used for research into energy conservation and advanced energy services, ranging from non-intrusive appliance load monitoring, demand response measures, tailored energy and retrofit advice, appliance usage analysis, consumption and time-use statistics and smart home/building automation.
https://pureportal.strath.ac.uk/en/datasets/ -electrical-load-measurements-cleaned/

This website provides access to the ECO data set (Electricity Consumption and Occupancy). The ECO data set is a comprehensive data set for non-intrusive load monitoring and occupancy detection research. It was collected in 6 Swiss households over a period of 8 months. For each of the households, the ECO data set provides:
	1 Hz aggregate consumption data. Each measurement contains data on current, voltage, and phase shift for each of the three phases in the household.
	1 Hz plug-level data measured from selected appliances.
	Occupancy information measured through a tablet computer (manual labeling) and a passive infrared sensor (in some of the households).

https://vs.inf.ethz.ch/res/show.html?what=eco-data

