'use strict';
let installPrompt=null;
const installButton=document.getElementById('install-app');
const installHelp=document.getElementById('install-help');
function installed(){return window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;}
function updateInstall(){installButton.hidden=installed();}
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;updateInstall();});
window.addEventListener('appinstalled',()=>{installPrompt=null;installButton.hidden=true;});
installButton.addEventListener('click',async()=>{if(installPrompt){const prompt=installPrompt;installPrompt=null;try{await prompt.prompt();await prompt.userChoice;}catch{installHelp.showModal();}}else installHelp.showModal();});
updateInstall();
if('serviceWorker' in navigator){window.addEventListener('load',()=>{navigator.serviceWorker.register('/sw.js').catch(()=>{/* Editing remains available without offline installation support. */});});}
