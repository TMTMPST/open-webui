<script lang="ts">
	import { getContext, onMount, onDestroy } from 'svelte';
	import { WEBUI_API_BASE_URL } from '$lib/constants';

	type Attempt = {
		id: string;
		state: 'starting' | 'waiting' | 'verifying' | 'connected' | 'failed' | 'cancelled';
		url: string | null;
		device_code: string | null;
		detail: string | null;
	};

	const i18n = getContext('i18n');
	const providers = [
		{ id: 'chatgpt', name: 'ChatGPT' },
		{ id: 'claude', name: 'Claude' }
	];
	let enabled = false;
	let attempts: Record<string, Attempt> = {};
	let errors: Record<string, string> = {};
	let busy: Record<string, boolean> = {};
	let claudeCode = '';
	let timer: ReturnType<typeof setTimeout>;
	let disposed = false;
	const pending = (attempt?: Attempt) =>
		attempt && ['starting', 'waiting', 'verifying'].includes(attempt.state);

	async function request(path: string, method = 'GET', code?: string) {
		const response = await fetch(`${WEBUI_API_BASE_URL}/auths/subscription-login/${path}`, {
			method,
			headers: {
				Authorization: `Bearer ${localStorage.token}`,
				'Content-Type': code === undefined ? 'application/json' : 'application/octet-stream'
			},
			body: code
		});
		if (!response.ok) {
			const result = await response.json().catch(() => null);
			throw new Error(
				typeof result?.detail === 'string' ? result.detail : $i18n.t('Could not update sign-in.')
			);
		}
		return response.json();
	}

	function schedulePoll() {
		clearTimeout(timer);
		if (!disposed && Object.values(attempts).some(pending)) timer = setTimeout(poll, 1500);
	}

	async function poll() {
		await Promise.all(
			providers.map(async ({ id }) => {
				const attempt = attempts[id];
				if (!pending(attempt) || busy[id]) return;
				try {
					const next = await request(`${id}/${attempt.id}`);
					if (!disposed && attempts[id] === attempt && !busy[id]) {
						attempts[id] = next;
						errors[id] = '';
					}
				} catch (error) {
					if (!disposed && attempts[id] === attempt && !busy[id]) {
						errors[id] = (error as Error).message;
						attempts[id] = { ...attempt, state: 'failed', url: null, device_code: null };
					}
				}
			})
		);
		schedulePoll();
	}

	async function act(id: string, action: 'start' | 'cancel' | 'code') {
		if (busy[id]) return;
		busy[id] = true;
		errors[id] = '';
		const code = action === 'code' ? claudeCode.trim() : undefined;
		if (id === 'claude') claudeCode = '';
		try {
			const path = action === 'start' ? id : `${id}/${attempts[id].id}`;
			attempts[id] = await request(
				action === 'code' ? `${path}/code` : path,
				action === 'cancel' ? 'DELETE' : 'POST',
				code
			);
		} catch (error) {
			errors[id] = (error as Error).message;
		} finally {
			busy[id] = false;
			schedulePoll();
		}
	}

	onMount(async () => {
		try {
			enabled = (await request('availability')).enabled === true;
		} catch {
			// The integration is opt-in and may be unavailable on older backends.
		}
	});
	onDestroy(() => {
		disposed = true;
		clearTimeout(timer);
	});
</script>

{#if enabled}
	<section class="mb-4 rounded-xl border border-gray-100 p-4 dark:border-gray-800" aria-label={$i18n.t('Personal subscription sign-in')}>
		<h2 class="text-sm font-semibold">{$i18n.t('Personal subscription sign-in')}</h2>
		<p class="mt-1 text-xs text-gray-500">
			{$i18n.t('Connect the CLI on this server. This does not install or enable a chat model.')}
		</p>
		<div class="mt-3 grid gap-3 sm:grid-cols-2">
			{#each providers as { id, name } (id)}
				{@const attempt = attempts[id]}
				<div class="space-y-2 rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
					<h3 class="text-sm font-medium">{name}</h3>
					<div class="space-y-2 text-xs" aria-live="polite">
						{#if attempt?.state === 'connected'}
							<p>{$i18n.t('Sign-in complete. Select the matching subscription model in a new chat.')}</p>
						{:else if attempt?.state === 'starting' || attempt?.state === 'verifying'}
							<p>{$i18n.t('Waiting for the CLI…')}</p>
						{:else if attempt?.state === 'cancelled'}
							<p>{$i18n.t('Sign-in cancelled.')}</p>
						{/if}
						{#if attempt?.detail || errors[id]}
							<p role="alert" class="text-red-600 dark:text-red-400">{errors[id] || attempt.detail}</p>
						{/if}
						{#if attempt?.url}
							<a href={attempt.url} target="_blank" rel="noopener noreferrer" class="underline">
								{$i18n.t('Open official sign-in page')}
							</a>
							{#if id === 'chatgpt' && attempt.device_code}
								<p>{$i18n.t('Enter this code on the official page:')} <code class="select-all">{attempt.device_code}</code></p>
							{:else if id === 'claude'}
								<form class="space-y-2" on:submit|preventDefault={() => act(id, 'code')}>
									<label class="block">
										{$i18n.t('If Claude shows a one-time code, enter it here:')}
										<input type="password" autocomplete="off" maxlength="2048" bind:value={claudeCode} class="mt-1 block w-full rounded-md border border-gray-200 bg-transparent px-2 py-1.5 dark:border-gray-700" />
									</label>
									<button type="submit" disabled={busy[id] || !claudeCode.trim()} class="rounded-md border border-gray-200 px-2 py-1 disabled:opacity-50 dark:border-gray-700">{$i18n.t('Verify code')}</button>
								</form>
							{/if}
						{/if}
					</div>
					<button type="button" disabled={busy[id]} on:click={() => act(id, pending(attempt) ? 'cancel' : 'start')} class="rounded-md border border-gray-200 px-2 py-1 text-xs disabled:opacity-50 dark:border-gray-700">
						{pending(attempt) ? $i18n.t('Cancel') : $i18n.t('Connect {{provider}}', { provider: name })}
					</button>
				</div>
			{/each}
		</div>
	</section>
{/if}
