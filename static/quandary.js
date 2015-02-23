// None of this is used anymore
//

function fetchGroupList() {
    var list = $("#group-list-form");
    FB.api("me/groups?fields=icon,name", function(response) {
        for (var i = 0; i < response.data.length; i++) {
            var group = response.data[i];
            var option = "<div class='group'><img src='" + group.icon + "'><input type='radio' name='group_id' value='" + group.id + "'><p>" + group.name + "</p></div>";     
            list.append(option);
        }
        list.append("<input type='submit' value='submit' style='float:right; margin-top:10px'>");
    });
}
  
  
function statusChangeCallback(response) {
    if (response.status === 'connected') {
        fetchGroupList();
        $(".fb-login-button").hide();
        $("#group-list-form").append("<input type='text' name='access_token' style='display:none' value='" + response.authResponse.accessToken + "'>"); //Kludge
        $("#group-list").show();
    } else {
        alert("Something went wrong. Please try again");
        $("#group-list").hide();
        $(".fb-login-button").show();
    }
}

  
function checkLoginState() {
    FB.getLoginStatus(function(response) {
        statusChangeCallback(response);
    });
}

  
window.fbAsyncInit = function() {
    FB.init({
        appId      : '626019544198223',
        cookie     : true,
        xfbml      : true,
        version    : 'v2.2'
    });
  
    FB.getLoginStatus(function(response) {
        statusChangeCallback(response);
    });
};

  
(function(d, s, id) {
    var js, fjs = d.getElementsByTagName(s)[0];
    if (d.getElementById(id)) return;
    js = d.createElement(s); js.id = id;
    js.src = "//connect.facebook.net/en_US/sdk.js";
    fjs.parentNode.insertBefore(js, fjs);
}(document, 'script', 'facebook-jssdk'));
