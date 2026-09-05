import {chromium} from '@playwright/test';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);const sharp=createRequire(require.resolve('next/package.json'))('sharp');
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'no-preference'});
try{
 await page.goto(process.env.E2E_BASE_URL||'http://localhost:3001');
 await page.locator('[data-planet][data-ready=true]').waitFor({timeout:60000});
 await page.waitForTimeout(6000);
 const buffer=await page.locator('[data-planet]').screenshot({style:'[data-landing] header,[data-landing] main,[data-landing]>[aria-hidden=true]:not(:has(canvas)),#contact,.skip-link,nextjs-portal{visibility:hidden!important}'});
 await sharp(buffer).webp({quality:86}).toFile('public/assets/earth/planet-poster.webp');
 console.log('Captured the adapted Ascend Earth poster');
}finally{await browser.close()}
