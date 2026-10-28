// OrbWorking de Aurora (thinking-orb-utils/orb-working.tsx), tal cual: el orbe de Procesar y de "Pensando".
import {BaseThinkingOrb} from './base-orb';
import type {ThinkingOrbProps} from './types';
export function OrbWorking(props:ThinkingOrbProps){return <BaseThinkingOrb mode="orbits" caption="Working" summary="Particles tracing tilted orbital rings around a ghosted sphere." {...props}/>}
