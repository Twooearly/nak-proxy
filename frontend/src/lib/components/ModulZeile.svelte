<script lang="ts">
	import type { Modul } from '#lib/api.js';
	import { Badge } from '#lib/components/ui/badge/index.js';
	import { Checkbox } from '#lib/components/ui/checkbox/index.js';
	import * as Select from '#lib/components/ui/select/index.js';

	let {
		modul,
		aktiv,
		gruppe,
		onToggle,
		onGruppe
	}: {
		modul: Modul;
		aktiv: boolean;
		gruppe: string | undefined;
		onToggle: (an: boolean) => void;
		onGruppe: (gruppe: string) => void;
	} = $props();

	const id = $derived(`modul-${modul.key}`);
	const istCode = $derived(/^[A-Z]{1,2}\d/.test(modul.key));
	const zeitraum = $derived.by(() => {
		const f = (iso: string) =>
			new Date(iso).toLocaleDateString('de-DE', { month: '2-digit', year: 'numeric' });
		const a = f(modul.erster_termin);
		const b = f(modul.letzter_termin);
		return a === b ? a : `${a} – ${b}`;
	});
</script>

<div class="flex flex-wrap items-center gap-x-3 gap-y-2 py-2">
	<Checkbox {id} checked={aktiv} onCheckedChange={(v) => onToggle(v === true)} />
	<label for={id} class="min-w-0 flex-1 cursor-pointer text-sm leading-snug">
		<span class={aktiv ? '' : 'text-muted-foreground line-through'}>{modul.titel}</span>
		<span class="text-muted-foreground block text-xs">
			{modul.anzahl_zukuenftig > 0
				? `${modul.anzahl_zukuenftig} von ${modul.anzahl} Terminen noch offen`
				: `${modul.anzahl} Termine · ${zeitraum}`}
		</span>
	</label>
	{#if istCode}
		<Badge variant="outline" class="font-mono">{modul.key}</Badge>
	{/if}
	{#if modul.gruppen.length > 1 && aktiv}
		<div class="basis-full pl-7 sm:basis-auto sm:pl-0">
		<Select.Root type="single" value={gruppe ?? ''} onValueChange={(v: string) => onGruppe(v)}>
			<Select.Trigger size="sm" class="w-36" aria-label="Laborgruppe für {modul.titel}">
				{gruppe ? `Gruppe ${gruppe}` : 'Alle Gruppen'}
			</Select.Trigger>
			<Select.Content>
				<Select.Item value="">Alle Gruppen</Select.Item>
				{#each modul.gruppen as g (g)}
					<Select.Item value={g}>Gruppe {g}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>
		</div>
	{/if}
</div>
