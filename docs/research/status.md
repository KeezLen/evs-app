Source: https://docs.google.com/document/d/1SSyIDZXrsuott-MbamfVE6Qx4e9U1sSYBPR_XgA1je0/edit
Retrieved: 2026-11-18

﻿Current status quo 
Project Energieverdienspel
17/11/2026 - KEN05




Data group:


We are currently using two datasets: Zonnedael and Gridflex. 
Zonnedael:
* Smartmeter data, with added weather data. Electricity in 15 minute intervals, gas in 60 minute intervals.
Gridflex:
* A much larger dataset (65 GB), re-sampled from 1 minute electricity and gas to 15 minutes of electricity and 60 minutes of gas. 


Event detection:
Implemented 3 different methods to detect anomalies in the (currently zonnedael) data. These 3 methods are:
* Basic rule based (as concept demonstrator)
* Isolation Forest
* RNN
The methods are evaluated on injected anomalies. These anomalies artificially make the electricity or gas usage higher or lower. This can happen in different intensities & durations. 


The current results look around the following: 
(also available through this link)    
  
These results should be taken with a grain of salt as there will be a lot of changes in the upcoming week(s). Namely the following:
* Updating to gridflex dataset (it was offline for a little bit)
* Changing train/test splits as we believe the current implementation did this in a possibly faulty way
* Optimizing these current algorithms based in general 
* Possibly adding another method (SVM)


Furthermore we are researching which types of detection these algorithms find so we can possibly filter out bad detections later on. 






Household profiling:


A tool was implemented to extract information about a household from the postcode, like the energy label, area, building type, building construction year, energy demand, heat demand, calculated energy use, temperature exceedance, compactness.


Tips group:
Implemented a rule-based recommendation system that selects energy-saving tips based on detected gas or electricity events, household information, season, and comfort conditions.


The system filters out unsuitable tips and ranks the remaining recommendations using TOPSIS based on:
-estimated saving
-ease
-priority.


It also includes personalized savings estimates, explanations for why a tip was selected, logging, and automated tests for the recommendation logic.


A user study was conducted comparing neutral tips with the same tips presented with a short positive compliment. Three representative tips were tested: lowering the thermostat by 1°C, washing at 30°C, and showering three minutes shorter.


Participants rated the tips on emotional response, understandability, feasibility, usefulness, willingness to follow, and trust.


The current results suggest that compliments had only a limited effect.
