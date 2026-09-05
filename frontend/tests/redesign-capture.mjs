import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
const out='../artifacts/redesign', base=process.env.E2E_BASE_URL||'http://localhost:3001';
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'no-preference'});
const evidence={errors:[],sections:[]};page.on('pageerror',e=>evidence.errors.push(e.message));
try{
 await page.goto(base);
 await page.locator('[data-planet][data-ready=true]').waitFor({timeout:60000});
 await page.waitForTimeout(6000);
 await page.screenshot({path:`${out}/hero-desktop.png`});
 for(const id of ['features','workflow','method','results','contact']){
  await page.evaluate(id=>document.getElementById(id).scrollIntoView(),id);
  await page.waitForTimeout(1500);
  if(id==='method'){await page.locator('[data-terrain][data-ready=true]').waitFor({timeout:30000});await page.waitForTimeout(500);}
  await page.screenshot({path:`${out}/${id}-desktop.png`});
  evidence.sections.push(await page.locator(`#${id}`).evaluate(e=>({id:e.id,height:e.getBoundingClientRect().height,vh:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth})));
 }
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.goto(`${base}/app`);
 await page.getByRole('heading',{name:'Рабочая карта',exact:true}).waitFor();
 await page.waitForFunction(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent==='Нарисовать контур');return b&&!b.disabled},{timeout:60000});
 await page.getByPlaceholder('Например, Potsdam').focus();
 await page.screenshot({path:`${out}/map-desktop.png`});
 for(const width of [320,390,768,1920]){
  await page.setViewportSize({width,height:width<700?844:1080});await page.goto(base);await page.waitForTimeout(500);
  for(const id of ['top','features','workflow','method','results','contact']){
   await page.evaluate(id=>document.getElementById(id).scrollIntoView(),id);await page.waitForTimeout(200);
   await page.screenshot({path:`${out}/${id}-${width}.png`});
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error(`Overflow ${id} ${width}`);
  }
 }
 if(evidence.errors.length)throw Error(evidence.errors.join('\n'));
 console.log(JSON.stringify(evidence));
}finally{await writeFile(`${out}/capture.json`,JSON.stringify(evidence,null,2));await browser.close()}
