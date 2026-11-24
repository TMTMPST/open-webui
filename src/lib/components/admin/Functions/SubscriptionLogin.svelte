<script lang="ts">
	import { getContext, onMount, onDestroy } from 'svelte';
	import { getModels } from '$lib/apis';
	import { getFunctions } from '$lib/apis/functions';
	import { functions, models } from '$lib/stores';
	import { WEBUI_API_BASE_URL } from '$lib/constants';

	type Connection = {
		connected: boolean;
		model_id: string | null;
		detail: string | null;
	};

	type Attempt = {
		id: string;
		state: 'starting' | 'waiting' | 'verifying' | 'connected' | 'failed' | 'cancelled';
		url: string | null;
		device_code: string | null;
		detail: string | null;
		connection: Connection | null;
	};

	const i18n = getContext('i18n');
	const providers = [
		{ id: 'chatgpt', name: 'ChatGPT' },
		{ id: 'claude', name: 'Claude' }
	];
	let enabled = false;
	let attempts: Record<string, Attempt> = {};
	let connections: Record<string, Connection | null> = {};
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

	async function refreshModels() {
		const [updatedModels, updatedFunctions] = await Promise.all([
			getModels(localStorage.token, false, true),
			getFunctions(localStorage.token)
		]);
		models.set(updatedModels);
		functions.set(updatedFunctions);
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
						if (next.connection) {
							connections[id] = next.connection;
							if (next.connection.model_id) {
								await refreshModels().catch(() => {
									errors[id] = $i18n.t('Could not refresh the model list. Reload this page.');
								});
							}
						}
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
			const state = await request('sync', 'POST');
			if (disposed || !state.enabled) return;
			enabled = true;
			for (const { id } of providers) {
				const { attempt, connection } = state.providers[id];
				if (attempt) attempts[id] = attempt;
				connections[id] = connection;
			}
			schedulePoll();
			if (Object.values(connections).some((connection) => connection?.model_id)) {
				await refreshModels().catch(() => {
					for (const { id } of providers) {
						if (connections[id]?.model_id) {
							errors[id] = $i18n.t('Could not refresh the model list. Reload this page.');
						}
					}
				});
			}
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
			{$i18n.t('Connect your subscription to add its chat model automatically. No API key is needed.')}
		</p>
		<div class="mt-3 grid gap-3 sm:grid-cols-2">
			{#each providers as { id, name } (id)}
				{@const attempt = attempts[id]}
				{@const connection = connections[id]}
				<div class="space-y-2 rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
					<h3 class="text-sm font-medium">{name}</h3>
					<div class="space-y-2 text-xs" aria-live="polite">
						{#if attempt?.state === 'starting' || attempt?.state === 'verifying'}
							<p>{$i18n.t('Waiting for the CLI…')}</p>
						{:else if attempt?.state === 'cancelled'}
							<p>{$i18n.t('Sign-in cancelled.')}</p>
						{:else if connection?.connected}
							<p>{$i18n.t('Connected')}</p>
						{:else if !pending(attempt)}
							<p>{$i18n.t('Not connected')}</p>
						{/if}
						{#if attempt?.detail || errors[id] || (!pending(attempt) && connection?.detail)}
							<p role="alert" class="text-red-600 dark:text-red-400">{errors[id] || attempt?.detail || connection?.detail}</p>
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
					{#if connection?.model_id && !pending(attempt)}
						<a href={`/?models=${encodeURIComponent(connection.model_id)}`} class="inline-block rounded-md border border-gray-200 px-2 py-1 text-xs dark:border-gray-700">
							{$i18n.t('Chat with {{provider}}', { provider: name })}
						</a>
					{:else if pending(attempt) || !connection?.connected}
						<button type="button" disabled={busy[id]} on:click={() => act(id, pending(attempt) ? 'cancel' : 'start')} class="rounded-md border border-gray-200 px-2 py-1 text-xs disabled:opacity-50 dark:border-gray-700">
							{pending(attempt) ? $i18n.t('Cancel') : $i18n.t('Connect {{provider}}', { provider: name })}
						</button>
					{/if}
				</div>
			{/each}
		</div>
	</section>
{/if}
