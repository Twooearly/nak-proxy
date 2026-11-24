<script lang="ts">
	// Logo neben dem Titel: Kachel mit Terminpunkten und Welle (gleiches Motiv wie favicon.svg).
	// Farben folgen dem Seitenthema (.dark), nicht nur der Systemeinstellung.
	let { class: klasse = '' }: { class?: string } = $props();
</script>

<svg viewBox="0 0 32 32" aria-hidden="true" class={klasse}>
	<rect x="2" y="2" width="28" height="28" rx="7" class="fill-[#1e3a8a] dark:fill-[#3b5bdb]" />
	<g fill="#fff">
		{#each [7, 12, 17, 22] as x (x)}
			<rect {x} y="8" width="3" height="3" rx="1" />
			<rect {x} y="13.5" width="3" height="3" rx="1" opacity={x === 17 ? 1 : 0.45} />
		{/each}
	</g>
	<path
		d="M2 22c3-2.5 6-2.5 9 0s6 2.5 9 0 6-2.5 10 0v1a7 7 0 0 1-7 7H9a7 7 0 0 1-7-7z"
		class="fill-[#3b82f6] dark:fill-[#60a5fa]"
	/>
</svg>
