function postLearnConfig(url, obj) { // eslint-disable-line no-unused-vars
    return new Promise(result => {
        fetch(url, {
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json'
            },
            method: "POST",
            body: JSON.stringify(obj)
        })
        .then(response => response.json())
        .then(data => {
                result(data);
            }
        )
    });
}

function postIgnoreButton(url, obj) { // eslint-disable-line no-unused-vars
    return new Promise(result => {
        fetch(url, {
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json'
            },
            method: "POST",
            body: JSON.stringify(obj)
        })
        .then(response => response.json())
        .then(data => {
                result(data);
            }
        )
    });
}
