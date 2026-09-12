(function(){
  var body=document.body,visual=document.getElementById('nfVisual'),video=document.getElementById('nfVideo');
  requestAnimationFrame(function(){body.classList.add('ready')});
  if(video){video.play().catch(function(){});}
  if(!visual||window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  var tx=0,ty=0,x=0,y=0;
  window.addEventListener('mousemove',function(e){tx=(e.clientX/window.innerWidth-.5)*34;ty=(e.clientY/window.innerHeight-.5)*26},{passive:true});
  function move(){x+=(tx-x)*.055;y+=(ty-y)*.055;visual.style.transform='translate3d('+x+'px,'+y+'px,0) scale(1.025)';requestAnimationFrame(move)}
  requestAnimationFrame(move);
})();
