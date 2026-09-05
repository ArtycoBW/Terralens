"use client";
import {useEffect,useRef} from "react";
import * as echarts from "echarts/core";
import {LineChart,ScatterChart,BarChart} from "echarts/charts";
import {GridComponent,TooltipComponent,LegendComponent,DataZoomComponent,MarkAreaComponent,AriaComponent} from "echarts/components";
import {CanvasRenderer} from "echarts/renderers";
import type {EChartsCoreOption} from "echarts/core";
echarts.use([LineChart,ScatterChart,BarChart,GridComponent,TooltipComponent,LegendComponent,DataZoomComponent,MarkAreaComponent,AriaComponent,CanvasRenderer]);
export function Chart({option,height=440,onDate}:{option:EChartsCoreOption;height?:number;onDate?:(date:string)=>void}){const el=useRef<HTMLDivElement>(null);const instance=useRef<echarts.EChartsType|null>(null);const select=useRef(onDate);useEffect(()=>{select.current=onDate;},[onDate]);useEffect(()=>{if(!el.current)return;const c=echarts.init(el.current,undefined,{renderer:"canvas"});instance.current=c;c.on("click",p=>{if(p.name)select.current?.(p.name);});const observer=new ResizeObserver(()=>c.resize());observer.observe(el.current);return()=>{observer.disconnect();c.dispose();instance.current=null;};},[]);useEffect(()=>{instance.current?.setOption({...option,animation:!window.matchMedia("(prefers-reduced-motion: reduce)").matches},true);},[option]);return <div ref={el} style={{height,width:"100%"}} role="img" aria-label="График временного ряда. Точные значения доступны в таблице ниже."/>}
