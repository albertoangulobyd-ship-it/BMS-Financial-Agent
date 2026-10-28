// Los tipos de los orbes de particulas de Aurora (thinking-orb-utils/types.ts), tal cual (sin
// ThinkingOrbDescriptor: la lista de orbes de thinking-orb.tsx no se porta, la app solo usa OrbWorking).
import type {CSSProperties} from 'react';
export type ThinkingOrbMode='orbits'|'globe'|'rubik'|'wave'|'web'|'braid'|'ribbon'|'ring'|'morph';
export type ThinkingOrbVariant='working'|'searching'|'solving'|'listening'|'connecting'|'weaving'|'composing'|'breathing'|'shaping';
export type ThinkingOrbSurface='auto'|'ink'|'paper'|'dark'|'light';
export interface ThinkingOrbProps{variant?:ThinkingOrbVariant|ThinkingOrbMode;surface?:ThinkingOrbSurface;size?:number;speed?:number;scale?:number;playback?:'play'|'pause';className?:string;style?:CSSProperties;caption?:string;summary?:string;frame?:readonly[number,number]}
export interface BaseThinkingOrbProps extends Omit<ThinkingOrbProps,'variant'>{mode?:ThinkingOrbMode}
