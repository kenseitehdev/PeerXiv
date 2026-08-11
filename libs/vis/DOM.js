
import { watch } from './Reactive.js';

// Efficient keyed diffing renderer
export function renderList(container, reactiveList, renderFn, keyFn = (item) => item.id || item.key || item) {
	let currentNodes = new Map();

	const update = (newList) => {
		const newNodes = new Map();
		const fragment = document.createDocumentFragment();

		// Mark existing nodes for reuse or removal
		newList.forEach((item, index) => {
			const key = keyFn(item, index);
			let node = currentNodes.get(key);

			if (!node) {
				node = renderFn(item, index);
			}

			newNodes.set(key, node);
			fragment.appendChild(node);
		});

		// Clear and replace container content
		container.innerHTML = '';
		container.appendChild(fragment);

		// Update node reference
		currentNodes = newNodes;
	};

	// Initial render + watch for changes
	watch(reactiveList, update);
}
