var db_stats_query = "{ Total_BGP_Updates: view_bgpupdates_aggregate { aggregate { count } } Total_Unhandled_Updates: view_bgpupdates_aggregate(where: {handled: {_eq: false}}) { aggregate { count } } Total_Hijacks: view_hijacks_aggregate { aggregate { count } } Resolved_Hijacks: view_hijacks_aggregate(where: {resolved: {_eq: true}}) { aggregate { count } } Mitigation_Hijacks: view_hijacks_aggregate(where: {under_mitigation: {_eq: true}}) { aggregate { count } } Ongoing_Hijacks: view_hijacks_aggregate(where: {active: {_eq: true}}) { aggregate { count } } Ignored_Hijacks: view_hijacks_aggregate(where: {ignored: {_eq: true}}) { aggregate { count } } Withdrawn_Hijacks: view_hijacks_aggregate(where: {withdrawn: {_eq: true}}) { aggregate { count } } Acknowledged_Hijacks: view_hijacks_aggregate(where: {seen: {_eq: true}}) { aggregate { count } } Outdated_Hijacks: view_hijacks_aggregate(where: {outdated: {_eq: true}}) { aggregate { count } } }";
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
function fetchDbStatsLive(ws, cb_func) {
    if(dbstatsCalled) {
        waitForConnection(ws, JSON.stringify({id: "1", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "1",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getLiveStats",
            query: "subscription getLiveStats " + db_stats_query
        }
    }));

    if(!dbstatsCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "1") {
                cb_func(data.payload.data);
            }
        });
        dbstatsCalled=true;
    }

}

var datatableCalled = false;
function stopDatatableLive(ws){
    waitForConnection(ws, JSON.stringify({id: "2", type: "stop"}));
}

function startDatatableLive(ws, query){
    waitForConnection(ws, JSON.stringify({
        id: "2",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getLiveTable",
            query: "subscription getLiveTable " + query
        }
    }));
}

function fetchDatatableLive(ws, cb_func, query) {
    if(datatableCalled) {
        waitForConnection(ws, JSON.stringify({id: "2", type: "stop"}));
    }

    waitForConnection(ws, JSON.stringify({
        id: "2",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getLiveTable",
            query: "subscription getLiveTable " + query
        }
    }));

    if(!datatableCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "2") {
                cb_func({
                    recordsTotal: data.payload.data.datatable.aggregate.totalCount,
                    recordsFiltered: data.payload.data.datatable.aggregate.totalCount,
                    data: format_datatable(data.payload.data.view_data)
                });
                $('.tooltip').tooltip('hide');
            }
        });
        datatableCalled = true;
    }
}

function fetchDatatable(cb_func, query) {
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
                query: "query getTable " + query
            })
        })
        .then(response => response.json())
        .then(data => {
                cb_func({
                    recordsTotal: data.data.datatable.aggregate.totalCount,
                    recordsFiltered: data.data.datatable.aggregate.totalCount,
                    data: format_datatable(data.data.view_data)
                });
            }
        )
        .catch(error => console.error(error));
    })
    .catch(error => console.error(error));
}

function fetchDistinctValues(type, query) {
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
                var list_of_values = [];
                $('.tooltip').tooltip('hide');
                if(type == 'origin_as' || type == 'peer_asn' || type == 'hijack_as'){
                    for(var elem in data['data']['view_data']){
                        list_of_values.push('<cc_as>' + data['data']['view_data'][elem][type] + '</cc_as>');
                    }
                    if(list_of_values[0] == "<cc_as>-1</cc_as>"){
                        list_of_values.shift();
                    }
                    $('#distinct_values_text').html(list_of_values.join(', '));
                    asn_map_to_name();
                }else if(type == 'service'){
                    for(var elem in data['data']['view_data']){
                        list_of_values.push(format_service(data['data']['view_data'][elem][type]));
                    }
                    $('#distinct_values_text').html(list_of_values.join(', '));
                    service_to_name();
                }else{
                    for(var elem in data['data']['view_data']){
                        list_of_values.push(data['data']['view_data'][elem][type]);
                    }
                    $('#distinct_values_text').text(list_of_values.join(', '));
                }
                $('#distinct_values_text').show();
            }
        )
        .catch(error => console.error(error));
    })
    .catch(error => console.error(error));
}

var processStateCalled = false;
function fetchProcStatesLive(ws, cb_func) {
    if(processStateCalled) {
        waitForConnection(ws, JSON.stringify({id: "3", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "3",
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
            if(data.type === 'data' && data.id === "3") {
                cb_func(data.payload.data);
            }
        });
        processStateCalled = true;
    }
}

var configStatsCalled = false;
function fetchConfigStatsLive(ws, cb_func) {
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

