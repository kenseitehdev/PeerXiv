
// Store.js
import { reactive } from './Reactive.js';

export function createStore({ state = {}, actions = {}, getters = {} }) {
	const reactiveState = reactive(state);

	// Bind actions to reactive state
	const boundActions = {};
	for (const key in actions) {
		boundActions[key] = (...args) => actions[key](reactiveState, ...args);
	}

	// Computed getters
	const computedGetters = {};
	for (const key in getters) {
		Object.defineProperty(computedGetters, key, {
			get: () => getters[key](reactiveState)
		});
	}

	return {
		state: reactiveState,
		actions: boundActions,
		getters: computedGetters
	};
}
