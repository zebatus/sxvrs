/*
* Replicates the functionality of jQuery's `load` function, 
* used to load some HTML from another file into the current one.
* 
* Based on this Stack Overflow answer:
* https://stackoverflow.com/a/38132775/3626537
* And `fetch` documentation:
* https://developer.mozilla.org/en-US/docs/Web/API/WindowOrWorkerGlobalScope/fetch
* 
* @param {string} parentElementId - The ID of the DOM element to load into
* @param {string} htmlFilePath - The path of the HTML file to load
*/
const loadHtml = function(parentElementId, filePath) {
    const init = {
        method : "GET",
        headers : { "Content-Type" : "text/html" },
        mode : "cors",
        cache : "default"
    };
    const req = new Request(filePath, init);
    fetch(req)
        .then(function(response) {
            return response.text();
        })
        .then(function(body) {
            // Replace `#` char in case the function gets called `querySelector` or jQuery style
            if (parentElementId.startsWith("#")) {
                parentElementId.replace("#", "");
            }
            document.getElementById(parentElementId).innerHTML = body;

        });
};
function setCookie(cname, cvalue, exdays) {
    var d = new Date();
    d.setTime(d.getTime() + (exdays*24*60*60*1000));
    var expires = "expires="+ d.toUTCString();
    document.cookie = cname + "=" + cvalue + ";" + expires + ";path=/";
}
function getCookie(cname) {
    var name = cname + "=";
    var decodedCookie = decodeURIComponent(document.cookie);
    var ca = decodedCookie.split(';');
    for(var i = 0; i <ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

function UpdateWidget(camera){
    if (camera == null) {
        [].forEach.call(widgets, function (el) {
            loadHtml(el.id, "/recorder/" + el.id + "/view_widget")
        });               
    } else{
        loadHtml(camera, "/recorder/" + camera + "/view_widget")
    }
}

function btn_click(self, camera_name, trg, cmd){
    self.style.display = "none"
    const url ='/recorder/' + camera_name + '/' + trg + '/' + cmd;
    const Http = new XMLHttpRequest();
    Http.open("GET", url);
    Http.send();
    Http.onreadystatechange = (e) => {
        console.log(Http.responseText)
    }
    setTimeout(function () {
        UpdateWidget(camera_name);
    }, 2000);
    
}
