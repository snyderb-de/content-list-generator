export namespace main {

	export class CloneCompareOptions {
	    driveA: string;
	    driveB: string;
	    outputDir: string;
	    hashAlgorithm: string;
	    softCompare: boolean;

	    static createFrom(source: any = {}) {
	        return new CloneCompareOptions(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.driveA = source["driveA"];
	        this.driveB = source["driveB"];
	        this.outputDir = source["outputDir"];
	        this.hashAlgorithm = source["hashAlgorithm"];
	        this.softCompare = source["softCompare"];
	    }
	}
	export class ScanOptions {
	    sourceDir: string;
	    outputDir: string;
	    outputFile: string;
	    hashAlgorithm: string;
	    excludeHidden: boolean;
	    excludeSystem: boolean;
	    createXLSX: boolean;
	    preserveZeros: boolean;
	    deleteCSV: boolean;
	    excludedExts: string;

	    static createFrom(source: any = {}) {
	        return new ScanOptions(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.sourceDir = source["sourceDir"];
	        this.outputDir = source["outputDir"];
	        this.outputFile = source["outputFile"];
	        this.hashAlgorithm = source["hashAlgorithm"];
	        this.excludeHidden = source["excludeHidden"];
	        this.excludeSystem = source["excludeSystem"];
	        this.createXLSX = source["createXLSX"];
	        this.preserveZeros = source["preserveZeros"];
	        this.deleteCSV = source["deleteCSV"];
	        this.excludedExts = source["excludedExts"];
	    }
	}

}

