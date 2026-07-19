function f(){
  var cards = [].slice.call(document.querySelectorAll(".weui-desktop-mass-media.weui-desktop-mass-appmsg"));
  var out = [];
  cards.forEach(function(card){
    var titleA = card.querySelector("a[href*='/s/']");
    var title = titleA ? titleA.textContent.replace(/\s*原创\s*$/, "").trim() : "";
    var ul = card.querySelector("a[href*='mpunderline']");
    var appmsg_id=null, send_time=null;
    if(ul){ var h=ul.getAttribute("href"); var m=h.match(/appmsg_id=(\d+)/); var s=h.match(/send_time=(\d+)/); appmsg_id=m?m[1]:null; send_time=s?s[1]:null; }
    var datas = [].slice.call(card.querySelectorAll(".weui-desktop-mass-media__data")).map(function(d){return (d.textContent||"").replace(/\s/g,"");});
    out.push({title:title, appmsg_id:appmsg_id, send_time:send_time, stats:datas});
  });
  return JSON.stringify(out);
}
f()
