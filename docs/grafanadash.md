*Many thanks to [Leonidas Poulopoulos](https://github.com/leopoul) for his contributions to this wiki page and ARTEMIS Grafana support!*

# What is Grafana?
Grafana is an analytics platform that allows for querying, visualising, alerting on and understanding metrics. It comes with an increasing variety of visualisation plugins that range from graphs, to heatmaps, to tables, to maps and supports multiple datasources like InfluxDB, Prometheus, Elasticsearch, MySQL, PostgreSQL, etc. More information about the supported plugins can be found [here](https://grafana.com/grafana/plugins).
Grafana documentation can be found [here](https://grafana.com/docs/). Please note that due to recent changes in Grafana UI the documentation on Grafana web site is not currently up to date (some screenshots come from previous versions).
For the sake of this page we will focus on:
- https://grafana.com/docs/administration/provisioning/
- https://grafana.com/docs/reference/templating/
- https://grafana.com/docs/features/datasources/postgres/

# Basic Grafana Terminology
* **Time viewing period**: It can be selected from the top right drop-down menu. There are presets (e.g., 3 hours ago) and the user can also define a time period. One thing to note is that depending on the data source used, and the aggregation function used to consolidate data points, selecting a very big time frame (e.g., 3 years ago) can have a negative impact on specific databases under specific circumstances.
* **Time Series data**: The "molecule" of an analytics platform. It's either periodic or arbitrary timestamped data in various forms (e.g., key/value, documents, multi-value, etv).
* **Vizualisation/Graph**: The representation of time-series data. Grafana can render graphs, tables, svgs, heatmaps, pie-charts, bar-gauges.
* **Dashboard**: a collection of graphs and/or vizualisations in general.
* **Provisioned dashboard**: A dashboard that has been created in a way that is bootstrapped when Grafana starts. See more below.
* **Non-provisioned dashboard**: A dashboard that the user can create and store in Grafana's DB (default: sqlite).

# Starting Grafana
By default, Artemis docker compose does not initiate the grafana container. This can be done via the following command:
```
docker-compose -f docker-compose.yaml -f docker-compose.grafana.yaml up -d
```
There are currently 3 Grafana-specific env variables that can be configured in the docker-compose.grafana.yaml file (note that by default the last 2 are commented):
```
GF_AUTH_ANONYMOUS_ENABLED: 'true'
#GF_SECURITY_ADMIN_USER: artemis
#GF_SECURITY_ADMIN_PASSWORD: artemispass
```
`GF_AUTH_ANONYMOUS_ENABLED` indicates whether we would like our dashboards to be accessible in read-only mode in public. The last 2 options change the default administrator username and password to whatever the user indicates via `GF_SECURITY_ADMIN_USER` and `GF_SECURITY_ADMIN_PASSWORD`.

For more options available the reader can check [this page](https://grafana.com/docs/installation/configuration/).

Once started (with default options), the Grafana container spins up the grafana instance at:
`http://<your server location>:8001` . The default username/password is **admin/admin** and **it is strongly suggested that it should change via the two variables mentioned above**.

# Built-in dashboards
Artemis comes with 4 built-in dashboards that can be modified and extended. The dashboard links show at the home page and are also accessible via the drop-down menu on the top left which currently shows "Home".

## Artemis::BGP Hijacks per prefix
It includes a bar-gauge at the top that shows the number of hijacks per prefix along with the prefix and the type of the hihjack. At the bottom, there is a breakdown of the (i) hijacks projected on a timeline indicating the time the hijack was detected, (ii) the number of (monitor) peers that have "seen" the hijack and (iii) the type of the hijack.
At the top there is an option to filter by hijack state and by hijacked prefix.

## Artemis::BGP Updates per prefix
It includes 3 bar-gauges showing total number of BGP updates, as well as announced and withdrawn prefixes. At the bottom there is a breakdown of the announcements/withdrawals projected on a timeline indicating the time the update was generated.
At the top there is an option to filter by prefix.

## Artemis::BGP Updates per service
It includes 3 bar gauges that show the number of total BGP updates, as well as announcements and withdrawals detected by the route-servers (monitoring services) used by Artemis.

## Artemis::Offending ASes
It includes 2 bar gauges that show the number of hijacks detected originating from an AS number both active and inactive for the current time-viewing period. At the bottom there is a breakdown per AS projected on time depending on the time that the hijack was detected by Artemis.

# Extending the dashboards/building your own
To extend a dashboard, a user needs to be first logged-in. Once logged-in, the user selects the dashboard they want to extend. Due to the way that Grafana dashboards were provisioned (see [this page](https://grafana.com/docs/administration/provisioning/)) changes on the existing dashboards cannot be made and saved. However Grafana provides the option of exporting provisioned dashboards in JSON format. Thus, it is suggested to save a provisioned dashboard with a new name and work on the new one for experimentation:
* To save an existing dashboard with a new name select the "Dashboard Settings" icon :gear: and on the left side of the new page select "Save As...". Select a new name and save.
* Each vizualisation plugin is rendered using data from ARTEMIS PostgreSQL. To inspect and/or modify a query move the cursor to the title of the plugin, click the small bottom arrow and select Edit. Remember you need to be logged-in to make changes.
* The query that renders the data is shown in the first section called queries. On the top of this section you can see the datasource which is defined in Grafana datasources and the actual query. Depending on the complexity of the query a user can go for the guided mode or the raw query mode and those can be swapped using the ✏️ icon. A recent presentation showing how datasources are added and dashboard are created can be found [here](https://youtu.be/-xlchgoqkqY?t=648).
* The power on Grafana lies in the dashboard variables. Imagine you monitor 100 prefixes. And imagine you wanted to build a graph for each. That would require a significant amount of effort. And then imagine that more prefixes were added or some were removed. More effort. Grafana solves this problem by introducing the concept of variables. The variables are derived from database queries that are executed whenever there is a page refresh (this can be configurable). For example, in the hijacks dashboard above, our variable is the configured prefix which we select from he database with a query. Then we configure grafana to use the result in the drop-down menu on the top left. Then we build the vizualisation for a single value and we configure the viszalisation to "repeat for" the range of values. Since the variables (e.g., hijacked prefixes) may change during each page refresh, our dashboard is up to date with new vizualisations (in this case it's the breakdown graphs that show at the bottom of the page in the Hijacks dashboard). More on using variables [here](https://grafana.com/docs/reference/templating/) and variables in postgresql [here](https://grafana.com/docs/features/datasources/postgres/#using-variables-in-queries).
* Once done with editing your dashboard, it's time to hit the world. All you need to do first, is save it; save frequently. Then in case you want your dashboard to become a provisioned dashboard you need to export it. Select the Share Dashboard icon on the top right, select the Export tab and turn on the External Sharing, then select Save to File... . By putting the json file under the grafana-provisioning/dashboards folder of ARTEMIS, you make your dashboard provisioned; it will be bootstrapped from the json file.
* _**Sometimes the JSON file includes an invalid definition at the top for the datasource, a fix is to replace every occurence of "${DS_ARTEMISPSQL}" with "ArtemisPSQL" in the generated JSON**_.
