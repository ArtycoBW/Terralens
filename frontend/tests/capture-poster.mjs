import {chromium} from "@playwright/test";
const browser=await chromium.launch({channel:"chrome",headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:"no-preference"});
try {
 await page.goto(process.env.E2E_BASE_URL||"http://localhost:3001/");
 await page.locator(".planet-canvas.ready").waitFor({timeout:60000});
 await page.waitForTimeout(4000);
 await page.screenshot({path:"public/assets/planet-poster.png",style:".marketing-nav,.marketing main,.marketing-footer,.skip-link,nextjs-portal {visibility:hidden!important}"});
 console.log("Captured poster from the supplied Ascend WebGL scene");
} finally {await browser.close();}
