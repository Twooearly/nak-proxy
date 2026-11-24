<script lang="ts">
	import { onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import CalendarIcon from '@lucide/svelte/icons/calendar-plus';
	import CheckIcon from '@lucide/svelte/icons/check';
	import CopyIcon from '@lucide/svelte/icons/copy';
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';

	import { aboPfad, ladeModule, ladeZenturien, type Modul, type Zenturie } from '#lib/api.js';
	import ModulZeile from '#lib/components/ModulZeile.svelte';
	import * as Alert from '#lib/components/ui/alert/index.js';
	import { Button } from '#lib/components/ui/button/index.js';
	import * as Card from '#lib/components/ui/card/index.js';
	import * as Collapsible from '#lib/components/ui/collapsible/index.js';
	import { Input } from '#lib/components/ui/input/index.js';
	import { Label } from '#lib/components/ui/label/index.js';
	import * as Select from '#lib/components/ui/select/index.js';
	import { Separator } from '#lib/components/ui/separator/index.js';

	let zenturien = $state<Zenturie[]>([]);
	let fehler = $state<string | null>(null);
	let laedt = $state(true);

	let studiengang = $state('');
	let jahrgang = $state('');
	let code = $state('');

	let module = $state<Modul[]>([]);
	let moduleLaden = $state(false);
	const ohne = new SvelteSet<string>();
	let gruppen = $state<Record<string, string>>({});
	let kopiert = $state(false);
	let origin = $state('');

	const name = (z: Zenturie) => z.studiengang ?? `Studiengang ${z.code[0]}`;

	const studiengaenge = $derived([...new Set(zenturien.map(name))].sort());
	const jahrgaenge = $derived(
		[...new Set(zenturien.filter((z) => name(z) === studiengang).map((z) => z.jahrgang))].sort(
			(a, b) => b - a
		)
	);
	const auswahl = $derived(
		zenturien.filter((z) => name(z) === studiengang && String(z.jahrgang) === jahrgang)
	);

	const aktuell = $derived(module.filter((m) => m.anzahl_zukuenftig > 0));
	const archiv = $derived(module.filter((m) => m.anzahl_zukuenftig === 0));
	const nachTyp = $derived.by(() => {
		const map = new Map<string, Modul[]>();
		for (const m of aktuell) map.set(m.typ_name, [...(map.get(m.typ_name) ?? []), m]);
		return [...map];
	});

	const pfad = $derived(code ? aboPfad(code, ohne, gruppen) : '');
	const url = $derived(pfad ? origin + pfad : '');
	const webcal = $derived(url.replace(/^https?:/, 'webcal:'));
	const google = $derived(
		`https://calendar.google.com/calendar/r?cid=${encodeURIComponent(webcal)}`
	);

	onMount(async () => {
		origin = location.origin;
		try {
			zenturien = await ladeZenturien();
		} catch {
			fehler = 'Die Zenturien konnten nicht geladen werden. Bitte später erneut versuchen.';
		} finally {
			laedt = false;
		}
		await ausHash();
	});

	// --- Auswahl ---------------------------------------------------------------

	function waehleStudiengang(v: string) {
		studiengang = v;
		jahrgang = jahrgaenge.length === 1 ? String(jahrgaenge[0]) : '';
		waehleJahrgang(jahrgang);
	}

	function waehleJahrgang(v: string) {
		jahrgang = v;
		void waehleZenturie(auswahl.length === 1 ? auswahl[0].code : '');
	}

	async function waehleZenturie(v: string, vorgabe?: { ohne: string[]; gruppen: Record<string, string> }) {
		code = v;
		ohne.clear();
		gruppen = {};
		module = [];
		if (!v) return;
		moduleLaden = true;
		try {
			module = await ladeModule(v);
			const keys = new Set(module.map((m) => m.key));
			for (const k of vorgabe?.ohne ?? []) if (keys.has(k)) ohne.add(k);
			gruppen = Object.fromEntries(
				Object.entries(vorgabe?.gruppen ?? {}).filter(([k]) => keys.has(k))
			);
		} catch {
			fehler = 'Die Module konnten nicht geladen werden.';
		} finally {
			moduleLaden = false;
		}
	}

	function toggle(key: string, an: boolean) {
		if (an) ohne.delete(key);
		else ohne.add(key);
	}

	function setzeGruppe(key: string, g: string) {
		const neu = { ...gruppen };
		if (g) neu[key] = g;
		else delete neu[key];
		gruppen = neu;
	}

	function alle(liste: Modul[], an: boolean) {
		for (const m of liste) toggle(m.key, an);
	}

	// --- Auswahl im Seiten-Hash merken (#/z/A25a.ics?ohne=...) --------------------

	$effect(() => {
		const ziel = pfad ? `#${pfad}` : '';
		if (location.hash !== ziel && !laedt) history.replaceState(null, '', ziel || location.pathname);
	});

	async function ausHash() {
		const m = location.hash.match(/^#\/z\/([A-Z]\d{2}[a-z])\.ics(?:\?(.*))?$/);
		if (!m) return;
		const z = zenturien.find((z) => z.code === m[1]);
		if (!z) return;
		const params = new URLSearchParams(m[2] ?? '');
		const liste = (p: string) => (params.get(p) ?? '').split(',').filter(Boolean);
		studiengang = name(z);
		jahrgang = String(z.jahrgang);
		await waehleZenturie(z.code, {
			ohne: liste('ohne'),
			gruppen: Object.fromEntries(liste('gruppe').map((g) => g.split('.', 2)))
		});
	}

	async function kopieren() {
		await navigator.clipboard.writeText(url);
		kopiert = true;
		setTimeout(() => (kopiert = false), 2000);
	}
</script>

<main class="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
	<header class="flex flex-col gap-2">
		<h1 class="text-2xl font-semibold tracking-tight">NAK Stundenplan-Abo</h1>
		<p class="text-muted-foreground text-sm">
			Wähle deine Zenturie und die Module, die in deinem Kalender erscheinen sollen. Du bekommst
			einen Abo-Link, der sich automatisch aktualisiert. Vergangene Termine bleiben erhalten,
			auch wenn die NAK sie aus dem Stundenplan nimmt.
		</p>
	</header>

	{#if fehler}
		<Alert.Root variant="destructive">
			<Alert.Title>Fehler</Alert.Title>
			<Alert.Description>{fehler}</Alert.Description>
		</Alert.Root>
	{/if}

	<Card.Root>
		<Card.Header>
			<Card.Title>1. Zenturie wählen</Card.Title>
		</Card.Header>
		<Card.Content class="grid grid-cols-2 gap-4">
			<div class="col-span-2 grid gap-2">
				<Label>Studiengang</Label>
				<Select.Root type="single" value={studiengang} onValueChange={waehleStudiengang} disabled={laedt}>
					<Select.Trigger class="w-full">{studiengang || (laedt ? 'Lädt …' : 'Auswählen')}</Select.Trigger>
					<Select.Content>
						{#each studiengaenge as s (s)}
							<Select.Item value={s}>{s}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
			<div class="grid gap-2">
				<Label>Studienbeginn</Label>
				<Select.Root type="single" value={jahrgang} onValueChange={waehleJahrgang} disabled={!studiengang}>
					<Select.Trigger class="w-full">{jahrgang || 'Jahr'}</Select.Trigger>
					<Select.Content>
						{#each jahrgaenge as j (j)}
							<Select.Item value={String(j)}>{j}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
			<div class="grid gap-2">
				<Label>Zenturie</Label>
				<Select.Root type="single" value={code} onValueChange={(v: string) => waehleZenturie(v)} disabled={!jahrgang}>
					<Select.Trigger class="w-full">{code || 'Zenturie'}</Select.Trigger>
					<Select.Content>
						{#each auswahl as z (z.code)}
							<Select.Item value={z.code}>{z.code}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
		</Card.Content>
	</Card.Root>

	{#if code}
		<Card.Root>
			<Card.Header>
				<Card.Title>2. Module auswählen</Card.Title>
				<Card.Description>
					Abgewählte Module fehlen im Abo. Neue Module, die später dazukommen, erscheinen
					automatisch.
				</Card.Description>
			</Card.Header>
			<Card.Content class="flex flex-col gap-4">
				{#if moduleLaden}
					<p class="text-muted-foreground text-sm">Module werden geladen …</p>
				{:else if module.length === 0}
					<p class="text-muted-foreground text-sm">Für diese Zenturie liegen noch keine Termine vor.</p>
				{:else}
					<div class="flex gap-2">
						<Button variant="outline" size="sm" onclick={() => alle(module, true)}>Alle</Button>
						<Button variant="outline" size="sm" onclick={() => alle(module, false)}>Keine</Button>
					</div>
					{#each nachTyp as [typ, liste] (typ)}
						<section>
							<h3 class="text-muted-foreground mb-1 text-xs font-medium uppercase tracking-wide">{typ}</h3>
							<div class="divide-y">
								{#each liste as m (m.key)}
									<ModulZeile
										modul={m}
										aktiv={!ohne.has(m.key)}
										gruppe={gruppen[m.key]}
										onToggle={(an) => toggle(m.key, an)}
										onGruppe={(g) => setzeGruppe(m.key, g)}
									/>
								{/each}
							</div>
						</section>
					{/each}
					{#if archiv.length}
						<Separator />
						<Collapsible.Root>
							<Collapsible.Trigger class="text-muted-foreground flex w-full items-center justify-between text-sm">
								Frühere Module im Archiv ({archiv.length})
								<ChevronDownIcon class="size-4" />
							</Collapsible.Trigger>
							<Collapsible.Content>
								<div class="divide-y pt-2">
									{#each archiv as m (m.key)}
										<ModulZeile
											modul={m}
											aktiv={!ohne.has(m.key)}
											gruppe={gruppen[m.key]}
											onToggle={(an) => toggle(m.key, an)}
											onGruppe={(g) => setzeGruppe(m.key, g)}
										/>
									{/each}
								</div>
							</Collapsible.Content>
						</Collapsible.Root>
					{/if}
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title>3. Abo-Link</Card.Title>
				<Card.Description>
					Diesen Link im Kalender als Abo hinzufügen, nicht als Datei importieren. Nur so
					bleibt er aktuell.
				</Card.Description>
			</Card.Header>
			<Card.Content class="flex flex-col gap-4">
				<div class="flex gap-2">
					<Input readonly value={url} class="font-mono text-xs" onfocus={(e: FocusEvent & { currentTarget: HTMLInputElement }) => e.currentTarget.select()} aria-label="Abo-Link" />
					<Button onclick={kopieren} class="shrink-0">
						{#if kopiert}<CheckIcon />Kopiert{:else}<CopyIcon />Kopieren{/if}
					</Button>
				</div>
				<div class="flex flex-wrap gap-2">
					<Button variant="outline" href={webcal}><CalendarIcon />Apple / Outlook</Button>
					<Button variant="outline" href={google} target="_blank" rel="noopener noreferrer">
						<CalendarIcon />Google Kalender
					</Button>
				</div>
				<ul class="text-muted-foreground list-disc space-y-1 pl-5 text-xs">
					<li>Apple Kalender: „Apple / Outlook“ antippen oder Ablage → Neues Kalenderabonnement.</li>
					<li>Google Kalender: Weitere Kalender → Per URL. Google aktualisiert Abos nur etwa alle 12–24 Stunden.</li>
					<li>Outlook: Kalender hinzufügen → Aus dem Internet abonnieren → Link einfügen.</li>
				</ul>
			</Card.Content>
		</Card.Root>
	{/if}

	<footer class="text-muted-foreground text-center text-xs">
		Inoffizielles Angebot, nicht von der Nordakademie. Die Daten stammen aus den öffentlichen
		Stundenplänen und werden alle 30 Minuten abgeglichen.
	</footer>
</main>
