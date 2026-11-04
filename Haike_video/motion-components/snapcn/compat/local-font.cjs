// Build-time replacement for Google font loaders. No font requests leave localhost.
const serif=/InstrumentSerif|SourceSerif|Ultra/;
exports.familyFor=name=>serif.test(name)?'Georgia, SimSun, serif':name==='Barlow'?'Arial Narrow, Microsoft YaHei, sans-serif':name==='Montserrat'?'Arial Black, Microsoft YaHei, sans-serif':'Arial, Haike Local, sans-serif';
