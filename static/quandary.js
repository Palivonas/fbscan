"use strict";

$(function(){
    $('body').on('keydown', '#token', function(e){
        if (e.keyCode == '13')
            listGroups($("#token").val());
    });
})

function getFormData() {
    var group = $("input:radio:checked").val();
    var token = $("input[name='access_token']").val()
    var limit = $("input[name='limit']").val()
    
    if (group === "custom") {
        group = $("input[name='custom_id']").val();
    }
    
    if (!group) {
        alert("Please select a group");
        return false;
    }
    else if (token.length == 0 || !token) {
        alert("Please insert an access token");
        return false;
    }
    else if (!Number(limit)) {
        alert("Invalid number of posts");
        return false;
    }
    
    document.cookie = "token=" + token;
    document.cookie = "group_id=" + group;
    
    var args = "group_id=" + group + "&access_token=" + token + "&limit=" + limit;
    $("#go").replaceWith("<img src='static/ajax-loader.gif' style='float:right; clear:both; margin-top:10px'>");
    
    $.get("/work?" + args);
    
    var interval = setInterval(function() {
        $.get("/dataready?group_id=" + group, function(response) {
            if (response == 1) {
                displayTab(args, "general", false, interval);
            }
        });
    }, 2000);
    
}


function getCookieData() {
    var cookie_strings = document.cookie.split("; "); 
    var cookie = {};
    for (var i = 0; i < cookie_strings.length; i++) {
        cookie[ cookie_strings[i].split("=")[0] ] = cookie_strings[i].split("=")[1];
    }
    return cookie;
}


function displayTab(args, tab, no_fade, interval) {
    if (interval) {
        clearInterval(interval);
    }
    
    $.get("/"+ tab +"?" + args, function(response) {
        var page = $("#container");
        
        if (!no_fade) {
            page.fadeOut(function() {
                page.empty();
                page.append(response);
                
                page.fadeIn();
                $(".tabs").fadeIn();
            });
        } else {
            page.empty();
            page.append(response);
            page.show();
            $(".tabs").show();
        }
    });
}


function changeTab(tab) {
    $("ul", "#options").hide();
    var cookie = getCookieData();
    displayTab($.param(cookie), tab);
}


function listGroups(token, no_fade) {
    if (token.length == 0) {
        return false;
    }
    var list = $("#group-list-form");
    
    // Gets the list of groups from Facebook
    $.getJSON("https://graph.facebook.com/v2.2/me/groups?fields=name,icon&access_token=" + token, function(response) {
        for (var i = 0; i < response.data.length; i++) {
            var group = response.data[i];
            var option = "<div class='group'><img src='" + group.icon + "'><input type='radio' name='group_id' value='" + group.id + "'><p>" + group.name + "</p></div>";
            list.append(option);
        }
        
        list.append("<div class='group'><img src='static/custom.png'><input type='radio' name='group_id' value='custom'><label>Custom ID: </label><input type='text' name='custom_id'></div>");
        list.append("Access token: <input type='text' style='margin: 10px 10px 0px 0px' name='access_token' value='" + token + "'><br>");
        list.append("Maximum number of posts to analyse: <input type='text' style='margin: 5px 10px 0px 0px' name='limit' value='100'><br>");
        list.append("<input type='button' id='go' onclick='getFormData()' value='Go!' style='float:right'>");
        
        if (no_fade) {
            $("#group-list").show();
        } else {
            $("#token-dialog").fadeOut(function() {
                $("#token-dialog").remove();
                $("#group-list").fadeIn();
            });
        }
        
    });
}


function resetGroup() {
    document.cookie = "group_id=";
}


function resetToken() {
    document.cookie = "token=";
}