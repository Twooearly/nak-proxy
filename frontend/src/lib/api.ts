// Typen und Helfer für die JSON-API des Flask-Backends (main.py)

export type Zenturie = {
	code: string;
	studiengang: string | null;
	jahrgang: number;
	letzter_abruf: string | null;
	letzter_termin: string | null;
};

export type Modul = {
	key: string;
	titel: string;
	typ: string | null;
	typ_name: string;
	anzahl: number;
	anzahl_zukuenftig: number;
	erster_termin: string;
	letzter_termin: string;
	gruppen: string[];
};

async function getJson<T>(url: string): Promise<T> {
	const res = await fetch(url);
	if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
	return res.json();
}

export const ladeZenturien = () => getJson<Zenturie[]>('/api/zenturien');

export const ladeModule = (code: string) =>
	getJson<Modul[]>(`/api/zenturien/${encodeURIComponent(code)}/module`);

/**
 * Baut den Query-String des Abos. Die Werte bestehen nur aus [A-Za-z0-9.-], deshalb ohne
 * Kodierung, damit Kommas lesbar bleiben. Sortiert, damit gleiche Auswahl = gleiche URL (Cache).
 */
export function aboPfad(code: string, ohne: Iterable<string>, gruppen: Record<string, string>) {
	const params: string[] = [];
	const o = [...ohne].sort();
	if (o.length) params.push(`ohne=${o.join(',')}`);
	const g = Object.entries(gruppen)
		.filter(([key]) => !o.includes(key))
		.map(([key, gr]) => `${key}.${gr}`)
		.sort();
	if (g.length) params.push(`gruppe=${g.join(',')}`);
	return `/z/${code}.ics${params.length ? '?' + params.join('&') : ''}`;
}
