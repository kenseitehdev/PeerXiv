import { selector } from './Selector.js';
import { defineComponent } from './Component.js';
import { reactive, computed } from './Reactive.js';
import { createStore } from './Store.js';
import { createRouter } from './Router.js';
import { renderList } from './DOM.js';
export const $ = {
	selector,
	component: {
		define: defineComponent
	},
	reactive,
	computed,
	store: {
		create: createStore
	},
	router: {
		create: createRouter
	},
    renderList
};
window.$=$;
