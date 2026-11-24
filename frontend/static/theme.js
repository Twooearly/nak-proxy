// Setzt das Farbschema vor dem ersten Rendern (kein helles Aufblitzen).
// Gespeicherte Wahl ('hell'/'dunkel') gewinnt, sonst gilt die Systemeinstellung.
// Liegt als Datei statt inline in app.html, damit die CSP ('self') ohne Hash auskommt.
(function () {
	var wahl = null;
	try {
		wahl = localStorage.getItem('theme');
	} catch (e) {}
	var dunkel =
		wahl === 'dunkel' ||
		(wahl !== 'hell' && window.matchMedia('(prefers-color-scheme: dark)').matches);
	document.documentElement.classList.toggle('dark', dunkel);
})();
