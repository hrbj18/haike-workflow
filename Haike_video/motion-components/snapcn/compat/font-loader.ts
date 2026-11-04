// Rendering fallback matches the local preview's caller-supplied Chinese font.
export function loadFont(){return {fontFamily:'Arial, Haike Local, sans-serif',waitUntilDone:()=>Promise.resolve()}}
export function getInfo(){return {fonts:{normal:{}}}}
