// Selector.js

class VSelector {
	constructor(selector) {
		this.elements = this.query(selector);
	}

	query(selector) {
		if (!selector) return [];
		if (selector instanceof Element) return [selector];
		if (Array.isArray(selector)) return selector;
		try {
			return Array.from(document.querySelectorAll(selector));
		} catch {
			console.warn(`Invalid selector: ${selector}`);
			return [];
		}
	}

css(type, styles = {}) {
	if (!["add", "remove", "toggle"].includes(type)) {
		console.warn(`Unknown css type: ${type}`);
		return this;
	}

	this.elements.forEach(el => {
		Object.entries(styles).forEach(([prop, value]) => {
			const current = el.style[prop];

			if (type === "add") {
				el.style[prop] = value;
			} else if (type === "remove") {
				el.style.removeProperty(prop);
			} else if (type === "toggle") {
				el.style[prop] = current === value ? "" : value;
			}
		});
	});
	return this;
}

	html(content) {
		this.elements.forEach(el => el.innerHTML = content);
		return this;
	}

	text(content) {
		this.elements.forEach(el => el.innerText = content);
		return this;
	}

	append(child) {
		this.elements.forEach(el => {
			if (child instanceof VSelector) {
				child.elements.forEach(c => el.appendChild(c));
			} else if (child instanceof Node) {
				el.appendChild(child);
			}
		});
		return this;
	}

	clear() {
		this.elements.forEach(el => el.innerHTML = "");
		return this;
	}

	addClass(...classNames) {
		this.elements.forEach(el => el.classList.add(...classNames));
		return this;
	}

	removeClass(...classNames) {
		this.elements.forEach(el => el.classList.remove(...classNames));
		return this;
	}

	toggleClass(className) {
		this.elements.forEach(el => el.classList.toggle(className));
		return this;
	}

	on(event, handler, options = false) {
		this.elements.forEach(el => {
			if (event === "hover") {
				el.addEventListener("mouseenter", handler, options);
				el.addEventListener("mouseleave", handler, options);
			} else {
				el.addEventListener(event, handler, options);
			}
		});
		return this;
	}

	off(event, handler) {
		this.elements.forEach(el => el.removeEventListener(event, handler));
		return this;
	}

	children() {
		return new VSelector(
			this.elements.flatMap(el => Array.from(el.children))
		);
	}

	find(subSelector) {
		return new VSelector(
			this.elements.flatMap(el => Array.from(el.querySelectorAll(subSelector)))
		);
	}

	each(callback) {
		this.elements.forEach((el, i) => callback(el, i));
		return this;
	}

	bind(reactiveVar) {
		this.elements.forEach(el => {
			if ("value" in el) {
				el.value = reactiveVar.value;
				el.addEventListener("input", () => reactiveVar.value = el.value);
				reactiveVar._watchers?.push(() => el.value = reactiveVar.value);
			}
		});
		return this;
	}
}

// Export as function
export const selector = (selector) => new VSelector(selector);
