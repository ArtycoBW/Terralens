"use client";
import {useEffect} from "react";
import gsap from "gsap";
import {ScrollTrigger} from "gsap/ScrollTrigger";
import Lenis from "lenis";
gsap.registerPlugin(ScrollTrigger);
export function LandingMotion(){useEffect(()=>{const match=gsap.matchMedia();match.add("(prefers-reduced-motion: no-preference)",()=>{const lenis=new Lenis({duration:1.1,smoothWheel:true,anchors:true});lenis.on("scroll",ScrollTrigger.update);const tick=(seconds:number)=>lenis.raf(seconds*1000);gsap.ticker.add(tick);const context=gsap.context(()=>{gsap.from(".marketing-hero [data-intro]",{y:25,duration:1.1,stagger:.1,ease:"power3.out",clearProps:"transform"});document.querySelectorAll(".marketing [data-reveal]").forEach(el=>{gsap.from(el,{y:32,opacity:.35,duration:.85,ease:"power2.out",scrollTrigger:{trigger:el,start:"top 92%",once:true},clearProps:"transform,opacity"});});});const pause=()=>{if(document.hidden)lenis.stop();else lenis.start();};document.addEventListener("visibilitychange",pause);return()=>{document.removeEventListener("visibilitychange",pause);context.revert();gsap.ticker.remove(tick);lenis.destroy();};});return()=>match.revert();},[]);return null}
