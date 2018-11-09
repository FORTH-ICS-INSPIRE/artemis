var db_stats_query = "{ Total_BGP_Updates: view_bgpupdates_aggregate { aggregate { count } } Total_Unhandled_Updates: view_bgpupdates_aggregate(where: {handled: {_eq: false}}) { aggregate { count } } Total_Hijacks: view_hijacks_aggregate { aggregate { count } } Resolved_Hijacks: view_hijacks_aggregate(where: {resolved: {_eq: true}}) { aggregate { count } } Mitigation_Hijacks: view_hijacks_aggregate(where: {under_mitigation: {_eq: true}}) { aggregate { count } } Ongoing_Hijacks: view_hijacks_aggregate(where: {active: {_eq: true}}) { aggregate { count } } Ignored_Hijacks: view_hijacks_aggregate(where: {ignored: {_eq: true}}) { aggregate { count } } Withdrawn_Hijacks: view_hijacks_aggregate(where: {withdrawn: {_eq: true}}) { aggregate { count } } Seen_Hijacks: view_hijacks_aggregate(where: {seen: {_eq: true}}) { aggregate { count } } }";
var proc_stats_query = "{ view_processes { name running timestamp } }";

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
                    recordsTotal: data.payload.data.view_hijacks_aggregate.aggregate.totalCount,
                    recordsFiltered: data.payload.data.view_hijacks_aggregate.aggregate.totalCount,
                    data: format_hijacks_datatable(data.payload.data.view_hijacks)
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

    // Need to remove previous event listener...
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
