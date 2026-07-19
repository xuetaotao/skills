function normTitle(s){
  // 统一空白：折叠所有空白字符 + 把 U+00A0 (nbsp) / U+3000 (全角空格) 转普通空格
  return (s || "").replace(/\u00A0|\u3000/g, " ").replace(/\s+/g, " ").replace(/\s*原创\s*$/,"").trim();
}

function f(){
  // ---- 1) 从页面嵌入的 publish_page JSON 取 send_time（含所有卡片，含转载/无 mpunderline 链接的）----
  function dec(s){ return s.replace(/&quot;/g,'"').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'); }
  function findClose(s, start){
    var depth=0, inStr=false, esc=false;
    for(var j=start;j<s.length;j++){
      var c=s[j];
      if(inStr){ if(esc) esc=false; else if(c==='\\') esc=true; else if(c==='"') inStr=false; }
      else { if(c==='"') inStr=true; else if(c==='{') depth++; else if(c==='}'){ depth--; if(depth===0) return j; } }
    }
    return -1;
  }
  var scripts=[].slice.call(document.scripts);
  var hit=scripts.filter(function(s){return /publish_list/.test(s.textContent);})[0];
  // 按「标题」建索引：send_time 与 DOM 卡片用标题配对，避免下标错位把时间安错文章
  var byTitle={};
  if(hit){
    try{
      var t=hit.textContent;
      var i=t.indexOf('{'); var close=findClose(t,i);
      var obj=eval('('+t.slice(i, close+1)+')');
      var pl=obj.publish_list||[];
      for(var k=0;k<pl.length;k++){
        var info=JSON.parse(dec(pl[k].publish_info));
        // appmsg_info 在新版后台是数组（旧版是对象）；两种结构都兼容
        var appmsg = Array.isArray(info.appmsg_info) ? info.appmsg_info[0] : info.appmsg_info;
        var title=normTitle(info.title || (appmsg && appmsg.title) || '');
        var st= info.sent_info ? info.sent_info.time : null;
        if(title) byTitle[title]=st;
      }
    }catch(e){ /* 忽略，回退 */ }
  }

  // ---- 2) 从 DOM 取 标题 / appmsg_id(用于详情页链接，必须与 d2_*.txt 命名一致) / 7 项统计数 ----
  function pickAppmsgId(card){
    var ul=card.querySelector("a[href*='mpunderline']");
    if(ul){ var m=(ul.getAttribute('href')||'').match(/appmsg_id=(\d+)/); if(m) return m[1]; }
    var rp=card.querySelector("a[href*='reprint']");
    if(rp){ var r=(rp.getAttribute('href')||'').match(/[?&]id=(\d+)/); if(r) return r[1]; }
    var any=card.querySelector("a[href*='appmsg_id=']");
    if(any){ var a=(any.getAttribute('href')||'').match(/appmsg_id=(\d+)/); if(a) return a[1]; }
    return null;
  }
  var domCards=[].slice.call(document.querySelectorAll(".weui-desktop-mass-media.weui-desktop-mass-appmsg"));
  var keys=Object.keys(byTitle);
  var out=[];
  for(var k=0;k<domCards.length;k++){
    var dc=domCards[k];
    var titleA=dc.querySelector("a[href*='/s/']");
    var title=titleA?normTitle(titleA.textContent):'';
    // 配对优先级：标题精确匹配 > 下标兜底（仅当 keys 长度与 domCards 长度差 ≤2，降低错位风险）
    var st=null;
    if(title && byTitle.hasOwnProperty(title)){
      st=byTitle[title];
    } else if(Math.abs(keys.length - domCards.length) <= 2 && keys[k]!==undefined){
      // 下标兜底：DOM 标题缺失或与嵌入不一致时，按下标取
      if(!title) title=keys[k];
      st=byTitle[keys[k]];
    }
    var stats=[].slice.call(dc.querySelectorAll(".weui-desktop-mass-media__data")).map(function(d){return (d.textContent||'').replace(/\s/g,'');});
    out.push({
      title: title,
      appmsg_id: pickAppmsgId(dc),
      send_time: st,
      stats: stats
    });
  }
  return JSON.stringify(out);
}
f()
