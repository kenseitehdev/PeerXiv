import { renderTemplate } from './Template.js';
import { watch, effect, reactive } from './Reactive.js';

class VComponent extends HTMLElement {
	constructor() {
		super();

		this.props = {};
		this.state = {};
		this._template = "";
		this._styles = "";
		this._lifecycle = {};
		this._observed = [];
		this._scopedClass = `v-${Math.random().toString(36).substring(2, 8)}`;
		this._watchers = [];
		this._content = null;
		this._cleanupFn = null;

		this.$watch = (ref, callback) => {
			const unsub = watch(ref, callback);
			if (typeof unsub === 'function') this._watchers.push(unsub);
		};

		this.update = (newProps = {}) => {
			for (const [key, val] of Object.entries(newProps)) {
				if (this.props[key]?.__isReactive) {
					this.props[key].value = val;
				} else {
					this.props[key] = reactive(val);
				}
			}
			this._renderWithEffect();
			this._invoke('update');
		};
	}

	connectedCallback() {
		this.classList.add(this._scopedClass);
		this.props = this._parseAttributes();
		if (this._styles) this._applyScopedStyles();
		this._renderWithEffect();
		void this._invoke('mount');
	}

	disconnectedCallback() {
		void this._invoke('destroy');
		this._removeScopedStyles();
		this._watchers.forEach(unsub => unsub());
		this._watchers = [];
	}

	_renderWithEffect() {
		if (!this._content) {
			this._content = document.createElement("div");
			this.appendChild(this._content);
		}

		if (this._cleanupFn) this._cleanupFn();

		this._cleanupFn = effect(() => {
			this._content.innerHTML = renderTemplate(this._template, this.props);
		});
	}

	attributeChangedCallback(attr, oldVal, newVal) {
		if (oldVal !== newVal) {
			if (this.props[attr]?.__isReactive) {
				this.props[attr].value = newVal;
			} else {
				this.props[attr] = reactive(newVal);
			}
			this.update();
		}
	}

	static get observedAttributes() {
		return this.prototype?._observed || [];
	}

	_parseAttributes() {
		const attrs = {};
		for (let attr of this.attributes) {
			let val = attr.value;
			try {
				val = JSON.parse(val);
			} catch (_) {
				// keep as string
			}
			attrs[attr.name] = reactive(val);
		}
		return attrs;
	}

	_applyScopedStyles() {
		if (!this._styleTag) {
			this._styleTag = document.createElement("style");
			this._styleTag.innerText = this._styles.replace(/:host|\.(\w+)/g, `.${this._scopedClass} .$1`);
			document.head.appendChild(this._styleTag);
		}
	}

	_removeScopedStyles() {
		if (this._styleTag && document.head.contains(this._styleTag)) {
			document.head.removeChild(this._styleTag);
		}
	}

	async _invoke(hook) {
		const fn = this._lifecycle[hook];
		if (typeof fn === "function") {
			try {
				await fn.call(this);
			} catch (err) {
				console.error(`Error in '${hook}' for ${this.tagName.toLowerCase()}:`, err);
			}
		}
	}
}

export function defineComponent({
	name,
	template,
	styles = "",
	props = [],
	methods = {},
	onMount,
	onUpdate,
	onDestroy
}) {
	if (!name || !template) throw new Error("Component must have a name and a template.");

	class CustomComponent extends VComponent {
		constructor() {
			super();
			this._template = template;
			this._styles = styles;
			this._lifecycle = {
				mount: onMount,
				update: onUpdate,
				destroy: onDestroy
			};
			this._observed = props;

			for (const [methodName, fn] of Object.entries(methods)) {
				this[methodName] = fn.bind(this);
			}
		}

		static get observedAttributes() {
			return props;
		}
	}

	if (!customElements.get(name)) {
		customElements.define(name, CustomComponent);
	}

	return (attributes = {}) => {
		const el = document.createElement(name);
		Object.entries(attributes).forEach(([key, val]) => el.setAttribute(key, val));
		return el;
	};
}
