var db_stats_query = `{
  Total_BGP_Updates: view_bgpupdates_aggregate {
    aggregate {
      count
    }
  }
  Total_Unhandled_Updates: view_bgpupdates_aggregate(where: {handled: {_eq: false}}) {
    aggregate {
      count
    }
  }
  Total_Hijacks: view_hijacks_aggregate {
    aggregate {
      count
    }
  }
  Resolved_Hijacks: view_hijacks_aggregate(where: {resolved: {_eq: true}}) {
    aggregate {
      count
    }
  }
  Mitigation_Hijacks: view_hijacks_aggregate(where: {under_mitigation: {_eq: true}}) {
    aggregate {
      count
    }
  }
  Ongoing_Hijacks: view_hijacks_aggregate(where: {active: {_eq: true}}) {
    aggregate {
      count
    }
  }
  Ignored_Hijacks: view_hijacks_aggregate(where: {ignored: {_eq: true}}) {
    aggregate {
      count
    }
  }
  Withdrawn_Hijacks: view_hijacks_aggregate(where: {withdrawn: {_eq: true}}) {
    aggregate {
      count
    }
  }
  Seen_Hijacks: view_hijacks_aggregate(where: {seen: {_eq: true}}) {
    aggregate {
      count
    }
  }
}`;

function fetchDbStatsLive(cb_func) {
    var ws = new WebSocket('wss://' + window.location.hostname + '/api/graphql', 'graphql-ws');

    ws.addEventListener('open', (event) => {
        ws.send(JSON.stringify({type:"connection_init",payload:{headers:{"Content-Type":"application/json","X-Hasura-Access-Key":"@rt3m1s."}}}));
        ws.send(JSON.stringify({
            id: "1",
            type: "start",
            payload: {
                variables: {},
                extensions: {},
                operationName: "getLive",
                query: "subscription getLive " + db_stats_query
            }
        }));
    });

    // Listen for messages
    ws.addEventListener('message', (event) => {
        data = JSON.parse(event.data);
        if(data.type === 'data') {
            cb_func(data.payload.data);
        }
    });

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
