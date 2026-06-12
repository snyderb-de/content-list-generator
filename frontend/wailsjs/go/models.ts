export namespace main {

	export class AgencyTemplateFields {
	    rg: string;
	    rcSeries: string;
	    deptOrganization: string;
	    division: string;
	    section: string;
	    unit: string;
	    rcSeriesName: string;
	    beginDate: string;
	    endDate: string;
	    description: string;
	    location: string;
	    materialType: string;
	    comments: string;
	    confidential: string;
	    dispositionDate: string;
	    boxNum: string;
	    tdNum: string;
	    locationId: string;
	    recordLevel: string;

	    static createFrom(source: any = {}) {
	        return new AgencyTemplateFields(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.rg = source["rg"];
	        this.rcSeries = source["rcSeries"];
	        this.deptOrganization = source["deptOrganization"];
	        this.division = source["division"];
	        this.section = source["section"];
	        this.unit = source["unit"];
	        this.rcSeriesName = source["rcSeriesName"];
	        this.beginDate = source["beginDate"];
	        this.endDate = source["endDate"];
	        this.description = source["description"];
	        this.location = source["location"];
	        this.materialType = source["materialType"];
	        this.comments = source["comments"];
	        this.confidential = source["confidential"];
	        this.dispositionDate = source["dispositionDate"];
	        this.boxNum = source["boxNum"];
	        this.tdNum = source["tdNum"];
	        this.locationId = source["locationId"];
	        this.recordLevel = source["recordLevel"];
	    }
	}
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
	    foldersOnly: boolean;
	    folderDepth: number;
	    agencyTemplate: boolean;
	    agencyFields: AgencyTemplateFields;

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
	        this.foldersOnly = source["foldersOnly"];
	        this.folderDepth = source["folderDepth"];
	        this.agencyTemplate = source["agencyTemplate"];
	        this.agencyFields = AgencyTemplateFields.createFrom(source["agencyFields"]);
	    }
	}

}
