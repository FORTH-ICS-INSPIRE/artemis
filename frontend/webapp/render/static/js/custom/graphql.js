
var proc_stats_query = "{ view_processes { name running timestamp } }";
var config_stats_query = "{ view_configs(limit: 1, order_by: {time_modified: desc}) { raw_config comment time_modified } }";

function waitForConnection(ws, message) {
    if (ws.readyState === 1) {
        ws.send(message);
    } else {
        setTimeout(() => waitForConnection(ws, message), 1000);
    }
}

var dbstatsCalled = false;
function fetchDbStatsLive(ws) { // eslint-disable-line no-unused-vars
    if(dbstatsCalled) {
        waitForConnection(ws, JSON.stringify({id: "1", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "1",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getIndexAllStats",
            query: "subscription getIndexAllStats " + hasura['subscription']['stats']['query']
        }
    }));

    if(!dbstatsCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "1") {
                hasura['data']['stats'] = data.payload.data.view_index_all_stats[0];
                hasura['extra']['stats_callback']();
            }
        });
        dbstatsCalled=true;
    }
}


var datatableCalled = false;
function stopDatatableLive(ws){ // eslint-disable-line no-unused-vars
    waitForConnection(ws, JSON.stringify({id: "2", type: "stop"}));
    waitForConnection(ws, JSON.stringify({id: "3", type: "stop"}));
}

function startDatatableLive(ws){ // eslint-disable-line no-unused-vars
    waitForConnection(ws, JSON.stringify({
        id: "2",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getLiveTableData",
            query: "subscription getLiveTableData " + hasura['subscription']['view_data']['query']
        }
    }));

    waitForConnection(ws, JSON.stringify({
        id: "3",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getLiveTableCount",
            query: "subscription getLiveTableCount " + hasura['subscription']['count']['query']
        }
    }));
}

async function fetchDatatableLive(ws) { // eslint-disable-line no-unused-vars
    if(datatableCalled) {
        waitForConnection(ws, JSON.stringify({id: "2", type: "stop"}));
        waitForConnection(ws, JSON.stringify({id: "3", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "2",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getLiveTableData",
            query: "subscription getLiveTableData " + hasura['subscription']['view_data']['query']
        }
    }));

    waitForConnection(ws, JSON.stringify({
        id: "3",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getLiveTableCount",
            query: "subscription getLiveTableCount " + hasura['subscription']['count']['query']
        }
    }));
    if(!datatableCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && (data.id === "2" || data.id === "3")){
                if(data.id === "2") {
                    hasura['data']['view_data'] = format_datatable(data.payload.data.view_data);

                }else if(data.id === "3") {
                    hasura['data']['count'] = data.payload.data.count_data.aggregate.count;
                }
                DatatableLiveCallRender();
            }
        });
        datatableCalled = true;
    }
}

function DatatableLiveCallRender(){
    hasura['extra']['table_callback']({
        recordsTotal: hasura['data']['count'],
        recordsFiltered: hasura['data']['count'],
        data: hasura['data']['view_data']
    });
    $('.tooltip').tooltip('hide');
}

function fetchByQuery(input_query) { // eslint-disable-line no-unused-vars
    return new Promise(result => {
        fetch("/jwt/auth", {
            method: "GET",
            credentials: 'include'
        })
        .then(response => response.json())
        .then(data => {
            fetch("/api/graphql", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization":"Bearer " + data['access_token']
                },
                body: JSON.stringify({
                    query: "query " + input_query
                })
            })
            .then(response => response.json())
            .then(data => {
                    return result(data);
                }
            )
            .catch(error => console.error(error));
        })
        .catch(error => console.error(error));
    });
}


function fetchDatatable() { // eslint-disable-line no-unused-vars
    fetch("/jwt/auth", {
        method: "GET",
        credentials: 'include'
    })
    .then(response => response.json())
    .then(data => {
        fetch("/api/graphql", {
            method: "POST",
            headers: {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization":"Bearer " + data['access_token']
            },
            body: JSON.stringify({
                query: "query getTable " + hasura['query']['query']
            })
        })
        .then(response => response.json())
        .then(data => {
                hasura['data']['view_data'] = format_datatable(data.data.view_data);
                hasura['data']['count'] = data.data.count_data.aggregate.count;
                DatatableLiveCallRender();
            }
        )
        .catch(error => console.error(error));
    })
    .catch(error => console.error(error));
}

function fetchDistinctValues(type, query) { // eslint-disable-line no-unused-vars
    fetch("/jwt/auth", {
        method: "GET",
        credentials: 'include'
    })
    .then(response => response.json())
    .then(data => {
        fetch("/api/graphql", {
            method: "POST",
            headers: {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization":"Bearer " + data['access_token']
            },
            body: JSON.stringify({
                query: "query getDistinctValues " + query
            })
        })
        .then(response => response.json())
        .then(data => {
                var list_of_values_html = [];
                var css_row = ['<div class="row">', '</div>'];
                $('.tooltip').tooltip('hide');

                if(data['data']['view_data'][0][type] == -1){ // Remove -1
                    data['data']['view_data'].shift();
                }

                for (var i = 0; i < data['data']['view_data'].length; i++) {
                    if(list_of_values_html.length == 0){
                        list_of_values_html.push(css_row[0]);
                    }else if(i % 6 == 0){
                        list_of_values_html.push(css_row[1]);
                        list_of_values_html.push("</br>");
                        list_of_values_html.push(css_row[0]);
                    }
                    if(type == 'origin_as' || type == 'peer_asn' || type == 'hijack_as'){
                        list_of_values_html.push('<div class="col-lg-2"><cc_as><input class="form-control" style="text-align:center;" type="text" value="');
                        list_of_values_html.push(data['data']['view_data'][i][type]);
                        list_of_values_html.push('" readonly></div></cc_as>');
                    }else if(type == 'service'){
                        list_of_values_html.push('<div class="col-lg-2"><service><input class="form-control" style="text-align:center;" type="text" value="');
                        list_of_values_html.push(data['data']['view_data'][i][type]);
                        list_of_values_html.push('" readonly></service></div>');
                    }else{
                        list_of_values_html.push('<div class="col-lg-2"><input class="form-control" style="text-align:center;" type="text" value="');
                        list_of_values_html.push(data['data']['view_data'][i][type]);
                        list_of_values_html.push('" readonly></div>');
                    }
                }
                $('#distinct_values_text').html(list_of_values_html.join(''));
                if(type == 'origin_as' || type == 'peer_asn' || type == 'hijack_as'){
                    asn_map_to_name();
                }else if(type == 'service'){
                    service_to_name();
                }
                $('#distinct_values_text').show();
            }
        )
        .catch(error => console.error(error));
    })
    .catch(error => console.error(error));
}

var processStateCalled = false;
function fetchProcStatesLive(ws, cb_func) { // eslint-disable-line no-unused-vars
    if(processStateCalled) {
        waitForConnection(ws, JSON.stringify({id: "4", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "4",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getStates",
            query: "subscription getStates " + proc_stats_query
        }
    }));

    if(!processStateCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "4") {
                cb_func(data.payload.data);
            }
        });
        processStateCalled = true;
    }
}

var configStatsCalled = false;
function fetchConfigStatsLive(ws, cb_func) { // eslint-disable-line no-unused-vars
    if(configStatsCalled) {
        waitForConnection(ws, JSON.stringify({id: "5", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "5",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getConfig",
            query: "subscription getConfig " + config_stats_query
        }
    }));

    if(!configStatsCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "5") {
                cb_func(data.payload.data);
            }
        });
        configStatsCalled = true;
    }
}

function fetchDBVersion() { // eslint-disable-line no-unused-vars
    fetch("/jwt/auth", {
        method: "GET",
        credentials: 'include'
    })
    .then(response => response.json())
    .then(data => {
        fetch("/api/graphql", {
            method: "POST",
            headers: {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization":"Bearer " + data['access_token']
            },
            body: JSON.stringify({
                query: "query getDBstats { view_data: view_db_details { version, upgraded_on } }"
            })
        })
        .then(response => response.json())
        .then(data => {
                $('#database_version').text(data['data']['view_data'][0].version)
            }
        )
        .catch(error => console.error(error));
    })
    .catch(error => console.error(error));
}

function fetchLatestConfig() { // eslint-disable-line no-unused-vars
    return new Promise(config => {
        fetch("/jwt/auth", {
            method: "GET",
            credentials: 'include'
        })
        .then(response => response.json())
        .then(data => {
            fetch("/api/graphql", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization":"Bearer " + data['access_token']
                },
                body: JSON.stringify({
                    query: "query getLatestConfig { view_data: view_configs( order_by: {time_modified: desc}, limit: 1 ) { raw_config, comment, time_modified } }"
                })
            })
            .then(response => response.json())
            .then(data => {
                    config(data['data']['view_data'][0]);
                }
            )
            .catch(error => console.error(error));
        })
        .catch(error => console.error(error));
    });
}

var fetchHijackByKeyCalled = false;
function fetchHijackByKeyLive(ws, hijack_key, trigger) { // eslint-disable-line no-unused-vars
    if(fetchHijackByKeyCalled) {
        waitForConnection(ws, JSON.stringify({id: "4", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "4",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getHijackByKey",
            query: "subscription getHijackByKey { view_hijacks(where: {key: {_eq:\"" + hijack_key + "\"}}, limit: 1) { key, type, prefix, hijack_as, num_peers_seen, num_asns_inf, time_started, time_ended, time_last, mitigation_started, time_detected, timestamp_of_config, under_mitigation, resolved, active, dormant, ignored, configured_prefix, comment, seen, withdrawn, peers_withdrawn, peers_seen, outdated, community_annotation, rpki_status } }"
        }
    }));

    if(!fetchHijackByKeyCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "4") {
                trigger(data.payload.data.view_hijacks[0]);
            }
        });
        fetchHijackByKeyCalled = true;
    }
}
