function postFetch_json(url, obj) { // eslint-disable-line no-unused-vars
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
        .catch(error => {
            if (error instanceof TypeError) {
                alert("Your session has expired")
                window.location.href = "/login"
            } else {
                console.error(error)
            }
        });
    });
}
