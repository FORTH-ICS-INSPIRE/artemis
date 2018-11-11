var db_stats_query = "{ Total_BGP_Updates: view_bgpupdates_aggregate { aggregate { count } } Total_Unhandled_Updates: view_bgpupdates_aggregate(where: {handled: {_eq: false}}) { aggregate { count } } Total_Hijacks: view_hijacks_aggregate { aggregate { count } } Resolved_Hijacks: view_hijacks_aggregate(where: {resolved: {_eq: true}}) { aggregate { count } } Mitigation_Hijacks: view_hijacks_aggregate(where: {under_mitigation: {_eq: true}}) { aggregate { count } } Ongoing_Hijacks: view_hijacks_aggregate(where: {active: {_eq: true}}) { aggregate { count } } Ignored_Hijacks: view_hijacks_aggregate(where: {ignored: {_eq: true}}) { aggregate { count } } Withdrawn_Hijacks: view_hijacks_aggregate(where: {withdrawn: {_eq: true}}) { aggregate { count } } Seen_Hijacks: view_hijacks_aggregate(where: {seen: {_eq: true}}) { aggregate { count } } }";
var proc_stats_query = "{ view_processes { name running timestamp } }";
var basic_proc_stats_query = '{ view_processes(where: {name: {_in: ["monitor","detection","mitigation"]}}) { name running timestamp } }';
var config_stats_query = "{ view_configs(limit: 1, order_by: {time_modified: desc}) { raw_config comment time_modified } }";

function waitForConnection(ws, message) {
    if (ws.readyState === 1) {
        ws.send(message);
    } else {
        setTimeout(() => waitForConnection(ws, message), 1000);
    }
};

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
        // Listen for messages
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
function update_datatable_called(ws, action){
    if (action == 'start'){
        datatableCalled = false;
    }else{
        datatableCalled = true;
    }
    waitForConnection(ws, JSON.stringify({id: "2", type: action}));
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
            operationName: "getLiveHij",
            query: "subscription getLiveHij " + query
        }
    }));

    // Need to remove previous event listener...
    if(!datatableCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "2") {
                cb_func({
                    recordsTotal: data.payload.data.datatable.aggregate.totalCount,
                    recordsFiltered: data.payload.data.datatable.aggregate.totalCount,
                    data: format_datatable(data.payload.data.view_data)
                });
            }
        });
        datatableCalled = true;
    }
    
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

var basicProcessStateCalled = false;
function fetchBasicProcStatesLive(ws, cb_func) {
    if(basicProcessStateCalled) {
        waitForConnection(ws, JSON.stringify({id: "4", type: "stop"}));
    }
    waitForConnection(ws, JSON.stringify({
        id: "4",
        type: "start",
        payload: {
            variables: {},
            extensions: {},
            operationName: "getBasicStates",
            query: "subscription getBasicStates " + basic_proc_stats_query
        }
    }));

    if(!basicProcessStateCalled) {
        ws.addEventListener('message', (event) => {
            data = JSON.parse(event.data);
            if(data.type === 'data' && data.id === "4") {
                cb_func(data.payload.data);
            }
        });
        basicProcessStateCalled = true;
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

function fetchDbStats() {
    return fetch("/api/graphql", {
        method: "POST",
        headers: {
            "X-Hasura-Access-Key": "@rt3m1s.",
            "Content-Type": "application/json; charset=utf-8"
        },
        body: JSON.stringify({
            query: 'query ' + db_stats_query
        })
    })
    .then(response => response.json())
    .catch(error => console.error(error));
}
